from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.text import slugify

from .models import CustomerProfile

User = get_user_model()


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
    }


def _generate_unique_username(base_name):
    candidate = slugify(base_name or 'user') or 'user'
    username = candidate
    suffix = 1

    while User.objects.filter(username=username).exists():
        username = f'{candidate}{suffix}'
        suffix += 1

    return username


def login_user(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)

    identifier = (request.POST.get('identifier') or '').strip()
    password = request.POST.get('password') or ''

    if not identifier or not password:
        return _json_error('Email/username and password are required.', status=400)

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
        return _json_error('Invalid credentials or inactive account.', status=401)

    login(request, user)
    return JsonResponse({
        'success': True,
        'message': 'Login successful.',
        'user': _serialize_user(user),
    }, status=200)


def logout_user(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)

    logout(request)
    return JsonResponse({'success': True, 'message': 'Logout successful.'}, status=200)


def register_user(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST is allowed.'}, status=405)

    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    submitted_role = (request.POST.get('role') or '').upper().strip()
    password = request.POST.get('password') or ''
    confirm_password = request.POST.get('confirm_password') or ''

    if not first_name or not last_name or not email or not password:
        return _json_error('First name, last name, email, and password are required.', status=400)

    if password != confirm_password:
        return _json_error('Passwords do not match.', status=400)

    if User.objects.filter(email__iexact=email).exists():
        return _json_error('An account with this email already exists.', status=400)

    if submitted_role != 'CUSTOMER':
        return _json_error('Public registration is restricted to CUSTOMER accounts only.', status=403)

    try:
        validate_password(password)
    except ValidationError as exc:
        return _json_error('Password validation failed.', status=400, extra={'errors': list(exc.messages)})

    username = _generate_unique_username(f'{first_name} {last_name}')

    try:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            role='CUSTOMER',
            is_active=True,
        )
    except IntegrityError:
        return _json_error('Unable to create the account with the supplied information.', status=400)

    CustomerProfile.create_for_customer(user)

    login(request, user)
    return JsonResponse({
        'success': True,
        'message': 'Registration successful.',
        'user': _serialize_user(user),
    }, status=201)


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
