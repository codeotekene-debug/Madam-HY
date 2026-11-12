import json
import uuid
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.products.models import Product
from .forms import (
    CustomerRequestCreateForm,
    RequestAssignForm,
    RequestStatusUpdateForm,
    StaffRequestCreateForm,
)
from .models import Request
from .services import RequestService

User = get_user_model()
STAFF_MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
    payload = {'success': success, 'message': message}
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    response = JsonResponse(payload, status=status)
    if data is not None and isinstance(data, dict):
        response.context = {**payload, **data}
    elif data is not None:
        response.context = payload
    return response


def _is_authenticated(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def _wants_json(request):
    format_param = (request.GET.get('format') or '').lower()
    if format_param == 'json':
        return True
    if format_param == 'html':
        return False
    content_type = request.content_type or request.headers.get('content-type', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('accept', '')
    if 'application/json' in accept:
        return True
    if 'text/html' in accept:
        return False
    return False


def _serialize_user(user):
    if user is None:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'role': user.role,
    }


def _serialize_product(product):
    if product is None:
        return None
    return {
        'id': product.id,
        'name': product.name,
        'sku': product.sku,
        'selling_price': str(product.selling_price) if hasattr(product, 'selling_price') else None,
    }


def _serialize_request(req):
    if req is None:
        return None

    # Build timeline from ActivityLog and timestamps
    timeline = []
    timeline.append({
        'title': 'Request submitted',
        'text': f'Submitted by {req.customer.get_full_name() or req.customer.username}.',
        'date': req.created_at.isoformat() if req.created_at else None,
    })

    try:
        content_type = ContentType.objects.get_for_model(Request)
        logs = ActivityLog.objects.filter(
            content_type=content_type,
            object_id=req.id,
        ).order_by('created_at')
        for log in logs:
            timeline.append({
                'title': log.action_label,
                'text': log.description,
                'date': log.created_at.isoformat(),
            })
    except Exception:
        pass

    if req.resolved_at and req.status in (Request.Status.COMPLETED, Request.Status.REJECTED, Request.Status.CANCELLED):
        timeline.append({
            'title': req.get_status_display(),
            'text': req.resolution or f'Request marked as {req.get_status_display()}.',
            'date': req.resolved_at.isoformat(),
        })

    return {
        'id': req.id,
        'uuid': str(req.uuid),
        'request_number': req.request_number,
        'customer': _serialize_user(req.customer),
        'customer_name': req.customer.get_full_name() or req.customer.username if req.customer else '',
        'request_type': req.request_type,
        'request_type_display': req.get_request_type_display(),
        'type': req.get_request_type_display(),
        'title': req.title,
        'description': req.description,
        'status': req.status,
        'status_display': req.get_status_display(),
        'priority': req.priority,
        'priority_display': req.get_priority_display(),
        'product': _serialize_product(req.product),
        'quantity': req.quantity,
        'assigned_to': _serialize_user(req.assigned_to),
        'assignee': req.assigned_to.get_full_name() or req.assigned_to.username if req.assigned_to else 'Unassigned',
        'resolution': req.resolution,
        'notes': req.notes,
        'attachment_url': req.attachment.url if req.attachment else None,
        'created_at': req.created_at.isoformat() if req.created_at else None,
        'created': req.created_at.isoformat() if req.created_at else None,
        'updated_at': req.updated_at.isoformat() if req.updated_at else None,
        'updated': req.updated_at.isoformat() if req.updated_at else None,
        'resolved_at': req.resolved_at.isoformat() if req.resolved_at else None,
        'timeline': timeline,
    }


def _get_request(request_id):
    """Retrieve Request by UUID, integer PK, or request_number."""
    if not request_id:
        return None
    id_str = str(request_id).strip()

    # Try UUID
    try:
        val = uuid.UUID(id_str)
        return Request.objects.select_related('customer', 'product', 'assigned_to').get(uuid=val)
    except (ValueError, TypeError, Request.DoesNotExist):
        pass

    # Try integer PK
    try:
        pk = int(id_str)
        return Request.objects.select_related('customer', 'product', 'assigned_to').get(pk=pk)
    except (ValueError, TypeError, Request.DoesNotExist):
        pass

    # Try request_number
    try:
        return Request.objects.select_related('customer', 'product', 'assigned_to').get(request_number__iexact=id_str)
    except Request.DoesNotExist:
        pass

    return None


def _parse_request_payload(request):
    """Parse JSON payload or request.POST data."""
    if request.body:
        content_type = request.content_type or request.headers.get('content-type', '')
        if 'application/json' in content_type:
            try:
                return json.loads(request.body.decode('utf-8')), None
            except (ValueError, UnicodeDecodeError):
                return None, {'detail': 'Malformed JSON in request body.'}
    data = {}
    for key, value in request.POST.items():
        data[key] = value
    return data, None


def request_list(request):
    """Staff/Management request list and customer-scoped request queue."""
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect(f'/accounts/login/?next={request.path}')

    is_customer = getattr(request.user, 'role', None) == 'CUSTOMER'

    # Base queryset with optimizations
    qs = Request.objects.select_related('customer', 'product', 'assigned_to')

    if is_customer:
        qs = qs.filter(customer=request.user)
    else:
        # Management filters
        customer_filter = (request.GET.get('customer') or '').strip()
        if customer_filter:
            if customer_filter.isdigit():
                qs = qs.filter(customer_id=int(customer_filter))
            else:
                qs = qs.filter(
                    Q(customer__username__icontains=customer_filter)
                    | Q(customer__email__icontains=customer_filter)
                    | Q(customer__first_name__icontains=customer_filter)
                    | Q(customer__last_name__icontains=customer_filter)
                )

        assignee_filter = (request.GET.get('assigned_to') or request.GET.get('assignee') or '').strip()
        if assignee_filter and assignee_filter.lower() != 'all':
            if assignee_filter.lower() == 'unassigned':
                qs = qs.filter(assigned_to__isnull=True)
            elif assignee_filter.lower() == 'me':
                qs = qs.filter(assigned_to=request.user)
            elif assignee_filter.isdigit():
                qs = qs.filter(assigned_to_id=int(assignee_filter))
            else:
                qs = qs.filter(assigned_to__username__icontains=assignee_filter)

    # Status filter
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter and status_filter.lower() != 'all':
        normalized_status = RequestService.normalize_status(status_filter)
        if normalized_status:
            qs = qs.filter(status=normalized_status)

    # Priority filter
    priority_filter = (request.GET.get('priority') or '').strip()
    if priority_filter and priority_filter.lower() != 'all':
        # Support "Medium" mapping to "NORMAL"
        if priority_filter.upper() == 'MEDIUM':
            priority_filter = 'NORMAL'
        normalized_priority = RequestService.normalize_priority(priority_filter)
        qs = qs.filter(priority=normalized_priority)

    # Request Type filter
    type_filter = (request.GET.get('type') or request.GET.get('request_type') or '').strip()
    if type_filter and type_filter.lower() != 'all':
        normalized_type = RequestService.normalize_request_type(type_filter)
        qs = qs.filter(request_type=normalized_type)

    # Keyword Search
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(request_number__icontains=search)
            | Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(customer__first_name__icontains=search)
            | Q(customer__last_name__icontains=search)
            | Q(customer__username__icontains=search)
            | Q(customer__email__icontains=search)
            | Q(assigned_to__first_name__icontains=search)
            | Q(assigned_to__last_name__icontains=search)
            | Q(assigned_to__username__icontains=search)
        )

    # Date range filters
    date_from_val = (request.GET.get('date_from') or '').strip()
    date_to_val = (request.GET.get('date_to') or '').strip()
    local_tz = timezone.get_current_timezone()
    if date_from_val:
        try:
            d_from = datetime.strptime(date_from_val, '%Y-%m-%d').date()
            qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(d_from, time.min), local_tz))
        except ValueError:
            pass
    if date_to_val:
        try:
            d_to = datetime.strptime(date_to_val, '%Y-%m-%d').date()
            qs = qs.filter(created_at__lte=timezone.make_aware(datetime.combine(d_to, time.max), local_tz))
        except ValueError:
            pass

    # Sorting
    sort_val = (request.GET.get('sort') or 'updated-desc').strip().lower()
    if sort_val == 'updated-asc':
        qs = qs.order_by('updated_at')
    elif sort_val == 'title-asc':
        qs = qs.order_by('title')
    elif sort_val == 'created-asc':
        qs = qs.order_by('created_at')
    elif sort_val == 'created-desc':
        qs = qs.order_by('-created_at')
    elif sort_val == 'priority-desc':
        # Order by priority descending
        qs = qs.order_by('-priority', '-updated_at')
    else:
        qs = qs.order_by('-updated_at', '-created_at')

    # Summary metrics for header cards
    summary = RequestService.get_summary_metrics(qs if is_customer else None)
    if is_customer:
        # Customer-specific summary based on all customer requests
        cust_all = Request.objects.filter(customer=request.user)
        summary = RequestService.get_summary_metrics(cust_all)

    # Pagination
    page_num = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    try:
        page_size = min(max(int(page_size), 1), 100)
    except (ValueError, TypeError):
        page_size = 20

    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    serialized_requests = [_serialize_request(r) for r in page_obj]

    if _wants_json(request):
        return _json_response(
            data={
                'requests': serialized_requests,
                'summary': summary,
                'pagination': {
                    'total_count': paginator.count,
                    'page': page_obj.number,
                    'page_size': page_size,
                    'total_pages': paginator.num_pages,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous(),
                },
            },
            message='Requests retrieved successfully.',
        )

    status_filter = (request.GET.get('status') or '').strip().upper()
    active_tab = 'pending' if status_filter == 'PENDING' else ('history' if status_filter in ('RESOLVED', 'COMPLETED') else 'all')
    template_name = 'customer/requests.html' if is_customer else 'requests/requests.html'
    context = {
        'requests': serialized_requests,
        'summary': summary,
        'page_obj': page_obj,
        'requests_data_json': json.dumps(serialized_requests),
        'active_module': 'requests',
        'active_tab': active_tab,
    }
    return render(request, template_name, context)


def customer_request_list(request):
    """Dedicated customer view for tracking own inquiries and requests."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect(f'/accounts/login/?next={request.path}')

    if getattr(request.user, 'role', None) != 'CUSTOMER' and getattr(request.user, 'role', None) not in STAFF_MANAGEMENT_ROLES:
        return _json_response(message='You do not have permission to access customer requests.', success=False, status=403)

    return request_list(request)


def request_create(request):
    """Submit a new request (Customer submission or Staff creating for customer)."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect(f'/accounts/login/?next={request.path}')

    is_customer = getattr(request.user, 'role', None) == 'CUSTOMER'

    if request.method == 'GET':
        if _wants_json(request):
            return _json_response(
                data={
                    'request_types': Request.RequestType.choices,
                    'priorities': Request.Priority.choices,
                },
                message='Request form metadata retrieved successfully.',
            )
        form = CustomerRequestCreateForm() if is_customer else StaffRequestCreateForm()
        template_name = 'requests/create_request.html'
        return render(request, template_name, {
            'form': form,
            'is_customer': is_customer,
            'active_module': 'requests',
            'active_tab': 'create',
        })

    if request.method != 'POST':
        return _json_response(message='Only GET and POST are allowed.', success=False, status=405)

    payload, json_err = _parse_request_payload(request)
    if json_err:
        return _json_response(message='Validation failed.', errors=json_err, success=False, status=400)

    # Determine customer target
    if is_customer:
        target_customer = request.user
    else:
        cust_id = payload.get('customer')
        if not cust_id:
            # If staff does not specify customer, reject with validation error
            return _json_response(message='Validation failed.', errors={'customer': 'Customer is required.'}, success=False, status=400)
        try:
            if str(cust_id).isdigit():
                target_customer = User.objects.get(pk=int(cust_id), role='CUSTOMER')
            else:
                target_customer = User.objects.get(username=str(cust_id).strip(), role='CUSTOMER')
        except User.DoesNotExist:
            return _json_response(message='Validation failed.', errors={'customer': 'Invalid or non-existent customer.'}, success=False, status=400)

    title = payload.get('title')
    description = payload.get('description')
    request_type = payload.get('request_type') or payload.get('type') or 'GENERAL'
    priority = payload.get('priority') or 'NORMAL'
    product = payload.get('product')
    quantity = payload.get('quantity')
    notes = payload.get('notes', '')
    attachment = request.FILES.get('attachment')

    try:
        new_request = RequestService.create_request(
            customer=target_customer,
            title=title,
            description=description,
            request_type=request_type,
            priority=priority,
            product=product,
            quantity=quantity,
            notes=notes,
            attachment=attachment,
            actor=request.user,
        )
    except ValidationError as e:
        errors = e.message_dict if hasattr(e, 'message_dict') else {'detail': e.messages}
        if _wants_json(request):
            return _json_response(message='Validation failed.', errors=errors, success=False, status=400)
        messages.error(request, 'Please correct the errors in your submission.')
        form = CustomerRequestCreateForm(request.POST, request.FILES) if is_customer else StaffRequestCreateForm(request.POST, request.FILES)
        return render(request, 'requests/create_request.html', {'form': form, 'errors': errors}, status=400)

    if _wants_json(request):
        return _json_response(
            data={'request': _serialize_request(new_request)},
            message='Request created successfully.',
            status=201,
        )

    messages.success(request, f'Request {new_request.request_number} created successfully.')
    if is_customer:
        return redirect(f'/requests/{new_request.uuid}/')
    return redirect(f'/requests/{new_request.uuid}/')


def request_detail(request, id):
    """View details of a request with object-level customer isolation."""
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect(f'/accounts/login/?next={request.path}')

    req = _get_request(id)
    if req is None:
        return _json_response(message='Request not found.', success=False, status=404)

    # Object-level Customer Isolation:
    # A customer can ONLY view their own requests.
    if getattr(request.user, 'role', None) == 'CUSTOMER':
        if req.customer_id != request.user.id:
            return _json_response(
                message='You do not have permission to view this request.',
                success=False,
                status=403,
            )

    serialized = _serialize_request(req)

    if _wants_json(request):
        return _json_response(
            data={'request': serialized},
            message='Request retrieved successfully.',
        )

    is_customer = getattr(request.user, 'role', None) == 'CUSTOMER'
    template_name = 'customer/request_detail.html' if is_customer else 'requests/request_detail.html'
    context = {
        'request_item': req,
        'request_detail': serialized,
        'request_detail_json': json.dumps(serialized),
        'active_module': 'requests',
        'active_tab': 'all',
    }
    return render(request, template_name, context)


def request_status_update(request, id):
    """Transition ticket lifecycle (Staff/Management only)."""
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    # Customer role is strictly rejected
    if getattr(request.user, 'role', None) == 'CUSTOMER':
        return _json_response(
            message='You do not have permission to update request status.',
            success=False,
            status=403,
        )

    req = _get_request(id)
    if req is None:
        return _json_response(message='Request not found.', success=False, status=404)

    payload, json_err = _parse_request_payload(request)
    if json_err:
        return _json_response(message='Validation failed.', errors=json_err, success=False, status=400)

    new_status = payload.get('status')
    if not new_status:
        return _json_response(message='Validation failed.', errors={'status': 'Status is required.'}, success=False, status=400)

    resolution = payload.get('resolution', '')
    notes = payload.get('notes', '')

    try:
        updated_req = RequestService.update_status(
            request_obj=req,
            new_status=new_status,
            actor=request.user,
            resolution=resolution,
            notes=notes,
        )
    except PermissionDenied as pe:
        return _json_response(message=str(pe), success=False, status=403)
    except ValidationError as ve:
        errors = ve.message_dict if hasattr(ve, 'message_dict') else {'detail': ve.messages}
        return _json_response(message='Validation failed.', errors=errors, success=False, status=400)

    if _wants_json(request):
        return _json_response(
            data={'request': _serialize_request(updated_req)},
            message=f'Request status updated to {updated_req.get_status_display()}.',
            status=200,
        )

    messages.success(request, f'Status updated to {updated_req.get_status_display()}.')
    return redirect(f'/requests/{updated_req.uuid}/')


def request_assign(request, id):
    """Assign or reassign request to a staff handler (Staff/Management only)."""
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    if getattr(request.user, 'role', None) == 'CUSTOMER':
        return _json_response(
            message='You do not have permission to assign requests.',
            success=False,
            status=403,
        )

    req = _get_request(id)
    if req is None:
        return _json_response(message='Request not found.', success=False, status=404)

    payload, json_err = _parse_request_payload(request)
    if json_err:
        return _json_response(message='Validation failed.', errors=json_err, success=False, status=400)

    assignee_val = payload.get('assigned_to') or payload.get('assignee')

    try:
        assigned_req = RequestService.assign_request(
            request_obj=req,
            staff_user=assignee_val,
            actor=request.user,
        )
    except PermissionDenied as pe:
        return _json_response(message=str(pe), success=False, status=403)
    except ValidationError as ve:
        errors = ve.message_dict if hasattr(ve, 'message_dict') else {'detail': ve.messages}
        return _json_response(message='Validation failed.', errors=errors, success=False, status=400)

    assignee_name = assigned_req.assigned_to.get_full_name() or assigned_req.assigned_to.username if assigned_req.assigned_to else 'Unassigned'
    if _wants_json(request):
        return _json_response(
            data={'request': _serialize_request(assigned_req)},
            message=f'Request assigned to {assignee_name}.',
            status=200,
        )

    messages.success(request, f'Request assigned to {assignee_name}.')
    return redirect(f'/requests/{assigned_req.uuid}/')
