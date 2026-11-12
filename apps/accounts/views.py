import json
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from .models import CustomerProfile

User = get_user_model()

STAFF_ROLES = {'OWNER', 'MANAGER', 'CASHIER', 'STAFF', 'RIDER'}


def _wants_json(request):
    """Determine if client requested a JSON response."""
    if request.GET.get('format') == 'json' or request.POST.get('format') == 'json':
        return True
    content_type = request.content_type or request.headers.get('content-type', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('accept', '')
    if 'application/json' in accept:
        return True
    return False


def _is_safe_redirect(url, request):
    """Validate that redirect target is safe and local."""
    if not url:
        return False
    return url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def user_has_role(user, roles):
    """Return True when the user matches one of the allowed roles."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False

    if isinstance(roles, str):
        allowed_roles = {roles}
    else:
        allowed_roles = set(roles)

    return user.role in allowed_roles


def _json_error(message, status=400, extra=None):
    payload = {'success': False, 'message': message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _serialize_user(user):
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'role': user.role,
        'phone_number': user.phone_number,
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'notification_preferences': user.get_notification_preferences(),
        'preferences': user.get_preferences(),
    }


def _generate_unique_username(base_name):
    candidate = slugify(base_name or 'user') or 'user'
    username = candidate
    suffix = 1

    while User.objects.filter(username=username).exists():
        username = f'{candidate}{suffix}'
        suffix += 1

    return username


@sensitive_post_parameters('password')
@csrf_protect
def login_user(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            from apps.accounts.services import get_role_redirect_url
            return redirect(get_role_redirect_url(request.user))
        next_url = request.GET.get('next', '')
        return render(request, 'accounts/login.html', {'next': next_url})

    if request.method != 'POST':
        if _wants_json(request):
            return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)
        return render(request, 'accounts/login.html', {'error': 'Method not allowed.'}, status=405)

    identifier = (request.POST.get('identifier') or '').strip()
    password = request.POST.get('password') or ''
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()

    if not identifier or not password:
        if _wants_json(request):
            return _json_error('Email/username and password are required.', status=400)
        return render(
            request,
            'accounts/login.html',
            {
                'error': 'Email/username and password are required.',
                'identifier': identifier,
                'next': next_url,
            },
            status=400,
        )

    user = None
    existing_user = None

    if '@' in identifier:
        existing_user = User.objects.filter(email__iexact=identifier).first()
    else:
        existing_user = User.objects.filter(username__iexact=identifier).first()

    if existing_user is not None:
        user = authenticate(request, email=existing_user.email, password=password)
        if user is None:
            user = authenticate(request, username=existing_user.username, password=password)
    else:
        user = authenticate(request, email=identifier, password=password)
        if user is None:
            user = authenticate(request, username=identifier, password=password)

    if user is None or not user.is_active:
        if _wants_json(request):
            return _json_error('Invalid credentials or inactive account.', status=401)
        return render(
            request,
            'accounts/login.html',
            {
                'error': 'Invalid credentials or inactive account.',
                'identifier': identifier,
                'next': next_url,
            },
            status=401,
        )

    login(request, user)

    try:
        from apps.activity_logs.services import log_activity
        log_activity(
            actor=user,
            action_type='SYSTEM',
            action_label='User Signed In',
            description=f"User {user.email or user.username} ({user.role}) signed in via login form.",
            related_object=user,
            metadata={
                'role': user.role,
                'portal': 'customer_login',
            },
            request=request,
        )
    except Exception:
        pass

    from apps.accounts.services import get_role_redirect_url
    role_default_url = get_role_redirect_url(user)

    if next_url and _is_safe_redirect(next_url, request):
        if user.role == 'CUSTOMER' and next_url.startswith('/dashboard'):
            redirect_url = role_default_url
        elif user.role in ('CASHIER', 'STAFF') and next_url.startswith('/reports'):
            redirect_url = role_default_url
        else:
            redirect_url = next_url
    else:
        redirect_url = role_default_url

    if _wants_json(request):
        return JsonResponse({
            'success': True,
            'message': 'Login successful.',
            'user': _serialize_user(user),
            'redirect_url': redirect_url,
        }, status=200)

    return redirect(redirect_url)


@sensitive_post_parameters('password')
@csrf_protect
def staff_login_view(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            from apps.accounts.services import get_role_redirect_url
            if getattr(request.user, 'role', None) in STAFF_ROLES:
                return redirect(get_role_redirect_url(request.user))
            return redirect('/customer/')
        next_url = request.GET.get('next', '')
        return render(request, 'accounts/staff_login.html', {'next': next_url})

    if request.method != 'POST':
        if _wants_json(request):
            return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)
        return render(request, 'accounts/staff_login.html', {'error': 'Method not allowed.'}, status=405)

    identifier = (request.POST.get('identifier') or '').strip()
    password = request.POST.get('password') or ''
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()

    if not identifier or not password:
        if _wants_json(request):
            return _json_error('Email/username and password are required.', status=400)
        return render(
            request,
            'accounts/staff_login.html',
            {
                'error': 'Email/username and password are required.',
                'identifier': identifier,
                'next': next_url,
            },
            status=400,
        )

    user = None
    existing_user = None

    if '@' in identifier:
        existing_user = User.objects.filter(email__iexact=identifier).first()
    else:
        existing_user = User.objects.filter(username__iexact=identifier).first()

    if existing_user is not None:
        user = authenticate(request, email=existing_user.email, password=password)
        if user is None:
            user = authenticate(request, username=existing_user.username, password=password)
    else:
        user = authenticate(request, email=identifier, password=password)
        if user is None:
            user = authenticate(request, username=identifier, password=password)

    if user is None or not user.is_active:
        if _wants_json(request):
            return _json_error('Invalid credentials or inactive account.', status=401)
        return render(
            request,
            'accounts/staff_login.html',
            {
                'error': 'Invalid credentials or inactive account.',
                'identifier': identifier,
                'next': next_url,
            },
            status=401,
        )

    if user.role not in STAFF_ROLES:
        error_msg = 'Access denied: Customer accounts cannot sign in through the Staff Portal.'
        if _wants_json(request):
            return _json_error(error_msg, status=403)
        return render(
            request,
            'accounts/staff_login.html',
            {
                'error': error_msg,
                'identifier': identifier,
                'next': next_url,
            },
            status=403,
        )

    login(request, user)

    try:
        from apps.activity_logs.services import log_activity
        log_activity(
            actor=user,
            action_type='SYSTEM',
            action_label='Staff Signed In',
            description=f"Staff member {user.email or user.username} ({user.role}) signed in via Staff Portal.",
            related_object=user,
            metadata={
                'role': user.role,
                'portal': 'staff_portal',
            },
            request=request,
        )
    except Exception:
        pass

    from apps.accounts.services import get_role_redirect_url
    role_default_url = get_role_redirect_url(user)

    if next_url and _is_safe_redirect(next_url, request):
        if user.role in ('CASHIER', 'STAFF') and next_url.startswith('/reports'):
            redirect_url = role_default_url
        else:
            redirect_url = next_url
    else:
        redirect_url = role_default_url

    if _wants_json(request):
        return JsonResponse({
            'success': True,
            'message': 'Staff login successful.',
            'user': _serialize_user(user),
            'redirect_url': redirect_url,
        }, status=200)

    return redirect(redirect_url)


def logout_user(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)

    logout(request)
    wants_json = (
        request.GET.get('format') == 'json'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
        or request.headers.get('x-requested-with') == 'XMLHttpRequest'
    )
    if wants_json:
        return JsonResponse({'success': True, 'message': 'Logout successful.'}, status=200)
    return redirect('accounts:login')


@sensitive_post_parameters('password', 'confirm_password')
@csrf_protect
def register_user(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            if getattr(request.user, 'role', None) == 'CUSTOMER':
                return redirect('/customer/')
            return redirect('/dashboard/')
        return render(request, 'accounts/register.html')

    if request.method != 'POST':
        if _wants_json(request):
            return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)
        return render(request, 'accounts/register.html', {'error': 'Method not allowed.'}, status=405)

    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    password = request.POST.get('password') or ''
    confirm_password = request.POST.get('confirm_password') or ''

    def _reg_error(message, status=400, extra=None):
        if _wants_json(request):
            return _json_error(message, status=status, extra=extra)
        return render(
            request,
            'accounts/register.html',
            {
                'error': message,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
            },
            status=status,
        )

    if not first_name or not last_name or not email or not password:
        return _reg_error('First name, last name, email, and password are required.', status=400)

    if password != confirm_password:
        return _reg_error('Passwords do not match.', status=400)

    if User.objects.filter(email__iexact=email).exists():
        return _reg_error('An account with this email already exists.', status=400)

    try:
        validate_password(password)
    except ValidationError as exc:
        return _reg_error(
            ' '.join(exc.messages) if not _wants_json(request) else 'Password validation failed.',
            status=400,
            extra={'errors': list(exc.messages)},
        )

    # Always strictly enforce CUSTOMER role; ignore any role passed in request.POST
    customer_role = getattr(getattr(User, 'Role', None), 'CUSTOMER', 'CUSTOMER')
    username = _generate_unique_username(f'{first_name} {last_name}')

    try:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            role=customer_role,
            is_active=True,
        )
    except IntegrityError:
        return _reg_error('Unable to create the account with the supplied information.', status=400)

    CustomerProfile.create_for_customer(user)

    login(request, user)

    try:
        from apps.activity_logs.services import log_activity
        log_activity(
            actor=user,
            action_type='CREATED',
            action_label='Customer Registered',
            description=f"New customer account created for {user.email}.",
            related_object=user,
            metadata={
                'role': customer_role,
                'source': 'public_registration',
            },
            request=request,
        )
    except Exception:
        pass

    if _wants_json(request):
        return JsonResponse({
            'success': True,
            'message': 'Registration successful.',
            'user': _serialize_user(user),
            'redirect_url': '/customer/',
        }, status=201)

    return redirect('/customer/')


def profile_view(request):
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Only GET is allowed.'}, status=405)

    if not request.user.is_authenticated:
        return _json_error('Authentication required.', status=401)

    return JsonResponse({'success': True, 'user': _serialize_user(request.user)}, status=200)


def change_password(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)

    if not request.user.is_authenticated:
        return _json_error('Authentication required.', status=401)

    current_password = request.POST.get('current_password') or ''
    new_password = request.POST.get('new_password') or ''
    confirm_password = request.POST.get('confirm_password') or ''

    if not current_password or not new_password or not confirm_password:
        return _json_error('Current password, new password, and confirmation are required.', status=400)

    if not request.user.check_password(current_password):
        return _json_error('Current password is incorrect.', status=400)

    if new_password != confirm_password:
        return _json_error('New passwords do not match.', status=400)

    try:
        validate_password(new_password, user=request.user)
    except ValidationError as exc:
        return _json_error('Password validation failed.', status=400, extra={'errors': list(exc.messages)})

    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])
    return JsonResponse({'success': True, 'message': 'Password updated successfully.'}, status=200)


def _parse_bool(value, field_name):
    """Safely parse boolean values or raise ValidationError."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in ('true', '1', 'on', 'yes'):
            return True
        if lower in ('false', '0', 'off', 'no'):
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValidationError(f"Invalid boolean value for '{field_name}'. Expected boolean (true/false).")


def customer_settings_view(request):
    """
    Render customer settings HTML page or return JSON preference state.
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Only GET is allowed.'}, status=405)

    wants_json = (
        request.GET.get('format') == 'json'
        or 'application/json' in request.headers.get('Accept', '')
    )

    if not request.user.is_authenticated:
        if wants_json:
            return _json_error('Authentication required.', status=401)
        login_url = reverse('accounts:login')
        return redirect(f"{login_url}?next={request.path}")

    if wants_json:
        return JsonResponse({
            'success': True,
            'user': _serialize_user(request.user),
            'preferences': request.user.get_preferences(),
            'notification_preferences': request.user.get_notification_preferences(),
        }, status=200)

    context = {
        'user': request.user,
        'preferences': request.user.get_preferences(),
        'notification_preferences': request.user.get_notification_preferences(),
        'settings_json': json.dumps(request.user.get_preferences()),
    }
    return render(request, 'customer/settings.html', context)


def customer_preferences_api(request):
    """
    GET/POST API endpoint for customer notification and experience preferences.
    Enforces customer isolation, input validation, and audit trail logging.
    """
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'success': False, 'message': 'Only GET and POST are allowed.'}, status=405)

    if not request.user.is_authenticated:
        return _json_error('Authentication required.', status=401)

    target_user_id = request.GET.get('user_id') or request.GET.get('customer_id')

    # GET: return current preferences
    if request.method == 'GET':
        if target_user_id and str(target_user_id) != str(request.user.id):
            if not (request.user.is_owner() or request.user.is_manager()):
                return _json_error('Cannot access preferences of another user.', status=403)
            target_user = User.objects.filter(id=target_user_id).first()
            if not target_user:
                return _json_error('Target user not found.', status=404)
        else:
            target_user = request.user

        return JsonResponse({
            'success': True,
            'user_id': target_user.id,
            'email': target_user.email,
            'preferences': target_user.get_preferences(),
            'notification_preferences': target_user.get_notification_preferences(),
        }, status=200)

    # POST: update preferences
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json_error('Malformed JSON payload.', status=400)
    else:
        data = request.POST.dict()

    if not isinstance(data, dict):
        return _json_error('Invalid request payload. Expected an object.', status=400)

    post_target_user_id = data.get('user_id') or data.get('customer_id') or target_user_id
    if post_target_user_id and str(post_target_user_id) != str(request.user.id):
        if not (request.user.is_owner() or request.user.is_manager()):
            return _json_error('Cannot modify preferences of another user.', status=403)
        target_user = User.objects.filter(id=post_target_user_id).first()
        if not target_user:
            return _json_error('Target user not found.', status=404)
    else:
        target_user = request.user

    # Notifications validation
    notifications_input = data.get('notifications')
    if notifications_input is not None and not isinstance(notifications_input, dict):
        return _json_error("Field 'notifications' must be an object/dict.", status=400)

    preferences_input = data.get('preferences')
    if preferences_input is not None and not isinstance(preferences_input, dict):
        return _json_error("Field 'preferences' must be an object/dict.", status=400)

    delivery_input = data.get('delivery')
    if delivery_input is not None and not isinstance(delivery_input, dict):
        return _json_error("Field 'delivery' must be an object/dict.", status=400)

    bool_fields = {
        'order_notifications': ['order_notifications', 'orders', 'orderNotifications'],
        'payment_notifications': ['payment_notifications', 'payments', 'paymentNotifications'],
        'request_notifications': ['request_notifications', 'requests', 'requestNotifications'],
        'promotion_notifications': ['promotion_notifications', 'promotions', 'promotionNotifications'],
    }

    parsed_updates = {}
    for model_field, aliases in bool_fields.items():
        val = None
        found = False
        for alias in aliases:
            if alias in data:
                val = data[alias]
                found = True
                break
        if not found and isinstance(notifications_input, dict):
            for alias in aliases:
                if alias in notifications_input:
                    val = notifications_input[alias]
                    found = True
                    break
        if found:
            try:
                parsed_updates[model_field] = _parse_bool(val, model_field)
            except ValidationError as exc:
                msg = exc.message if hasattr(exc, 'message') else str(exc)
                return _json_error(msg, status=400)

    # Extra preferences
    user_prefs = dict(target_user.preferences) if isinstance(target_user.preferences, dict) else {}
    prefs_changed = False

    # Language
    lang_val = None
    if isinstance(preferences_input, dict) and 'language' in preferences_input:
        lang_val = preferences_input['language']
    elif 'language' in data:
        lang_val = data['language']
    elif 'languageSelect' in data:
        lang_val = data['languageSelect']
    if lang_val is not None:
        lang_str = str(lang_val).strip()
        if user_prefs.get('language') != lang_str:
            user_prefs['language'] = lang_str
            prefs_changed = True

    # Currency
    curr_val = None
    if isinstance(preferences_input, dict) and 'currency' in preferences_input:
        curr_val = preferences_input['currency']
    elif 'currency' in data:
        curr_val = data['currency']
    elif 'currencySelect' in data:
        curr_val = data['currencySelect']
    if curr_val is not None:
        curr_str = str(curr_val).strip()
        if user_prefs.get('currency') != curr_str:
            user_prefs['currency'] = curr_str
            prefs_changed = True

    # Marketing emails
    mkt_val = None
    if isinstance(preferences_input, dict) and 'marketing' in preferences_input:
        mkt_val = preferences_input['marketing']
    elif 'marketingEmails' in data:
        mkt_val = data['marketingEmails']
    elif 'marketing' in data:
        mkt_val = data['marketing']
    if mkt_val is not None:
        try:
            parsed_mkt = _parse_bool(mkt_val, 'marketing')
            if user_prefs.get('marketing') != parsed_mkt:
                user_prefs['marketing'] = parsed_mkt
                prefs_changed = True
        except ValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return _json_error(msg, status=400)

    # Delivery
    deliv_val = None
    if isinstance(delivery_input, dict) and 'preferredMethod' in delivery_input:
        deliv_val = delivery_input['preferredMethod']
    elif 'preferred_delivery' in data:
        deliv_val = data['preferred_delivery']
    elif 'defaultDelivery' in data:
        deliv_val = data['defaultDelivery']
    if deliv_val is not None:
        deliv_str = str(deliv_val).strip()
        if user_prefs.get('preferred_delivery') != deliv_str:
            user_prefs['preferred_delivery'] = deliv_str
            prefs_changed = True

    previous_prefs = target_user.get_preferences()
    changes = {}
    update_fields = []

    for field, new_val in parsed_updates.items():
        old_val = getattr(target_user, field)
        if old_val != new_val:
            changes[field] = {'old': old_val, 'new': new_val}
            setattr(target_user, field, new_val)
            update_fields.append(field)

    if prefs_changed:
        changes['preferences'] = {
            'old': target_user.preferences if isinstance(target_user.preferences, dict) else {},
            'new': user_prefs,
        }
        target_user.preferences = user_prefs
        update_fields.append('preferences')

    if update_fields:
        target_user.save(update_fields=update_fields)

        try:
            from apps.activity_logs.services import log_activity
            log_activity(
                actor=request.user,
                action_type='UPDATED',
                action_label='Notification Preferences Updated',
                description=f"User {target_user.email} updated notification preferences.",
                related_object=target_user,
                metadata={
                    'changes': changes,
                    'before': previous_prefs,
                    'after': target_user.get_preferences(),
                },
                request=request,
            )
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'message': 'Preferences saved successfully.',
        'user_id': target_user.id,
        'preferences': target_user.get_preferences(),
        'notification_preferences': target_user.get_notification_preferences(),
    }, status=200)
