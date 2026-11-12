import json
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.decorators import role_required
from apps.delivery.decorators import delivery_management_required, rider_required
from apps.delivery.models import (
    Delivery,
    DeliverySetting,
    DeliveryStatusHistory,
    DeliveryZone,
    RiderProfile,
)
from apps.delivery.services import DeliveryService
from apps.orders.models import Order

User = get_user_model()


def _json_response(data=None, message='', success=True, status=200):
    return JsonResponse({
        'success': success,
        'message': message,
        'data': data or {},
    }, status=status)


def _json_error(message, status=400, errors=None):
    return JsonResponse({
        'success': False,
        'message': message,
        'errors': errors or {},
    }, status=status)


def _action_response(request, message, redirect_name=None, status=200):
    """Return JSON to API clients and a redirect after an ordinary form post."""
    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or '') or 'application/json' in (request.content_type or '')
    if wants_json:
        return _json_response(message=message, status=status)
    messages.success(request, message)
    return redirect(redirect_name or request.META.get('HTTP_REFERER') or 'delivery:management_dashboard')


def _parse_payload(request):
    """Parse JSON body or POST form data."""
    if 'application/json' in (request.content_type or ''):
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return {}
    return request.POST.dict()


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


# ==============================================================================
# RIDER PORTAL VIEWS
# ==============================================================================

@rider_required
def rider_dashboard_view(request):
    """4.1 Rider Dashboard."""
    data = DeliveryService.get_rider_dashboard_data(request.user)

    if request.GET.get('format') == 'json':
        return _json_response({
            'new_assignments_count': data['new_assignments_count'],
            'pending_pickups_count': data['pending_pickups_count'],
            'active_deliveries_count': data['active_deliveries_count'],
            'completed_count': data['completed_count'],
            'failed_count': data['failed_count'],
            'is_available': data['is_available'],
        })

    return render(request, 'rider/dashboard.html', data)


@rider_required
@require_POST
def rider_toggle_availability_api(request):
    """Toggle rider availability status."""
    profile = getattr(request.user, 'rider_profile', None)
    if not profile:
        profile = RiderProfile.objects.create(user=request.user)

    payload = _parse_payload(request)
    if 'is_available' in payload:
        new_val = _as_bool(payload['is_available'])
    else:
        new_val = not profile.is_available

    profile.is_available = new_val
    profile.status = (
        RiderProfile.RiderStatus.AVAILABLE if new_val else RiderProfile.RiderStatus.OFFLINE
    )
    profile.save(update_fields=['is_available', 'status', 'updated_at'])

    return _json_response(
        data={'is_available': profile.is_available, 'status': profile.status},
        message=f"Availability updated to {'Available' if profile.is_available else 'Offline'}.",
    )


@rider_required
def rider_assignments_view(request):
    """4.2 New Assignments page for rider."""
    assignments = Delivery.objects.filter(
        rider=request.user,
        status=Delivery.DeliveryStatus.ASSIGNED,
    ).select_related('order', 'zone').order_by('-assigned_at')

    if request.GET.get('format') == 'json':
        return _json_response({
            'assignments': [
                {
                    'id': d.id,
                    'tracking_number': d.tracking_number,
                    'order_number': d.order.order_number,
                    'customer_name': d.customer_name,
                    'customer_phone': d.customer_phone,
                    'delivery_address': d.delivery_address,
                    'delivery_instructions': d.delivery_instructions,
                    'delivery_fee': str(d.delivery_fee),
                    'assigned_at': d.assigned_at.isoformat() if d.assigned_at else None,
                }
                for d in assignments
            ]
        })

    return render(request, 'rider/assignments.html', {'assignments': assignments})


@rider_required
@require_POST
def rider_accept_delivery_api(request, delivery_id):
    """Accept an assigned delivery job."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    try:
        DeliveryService.rider_accept_delivery(delivery, request.user)
        messages.success(request, f"Delivery for Order {delivery.order.order_number} accepted.")
        return _action_response(request, "Delivery accepted successfully.", 'delivery:rider_assignments')
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@rider_required
@require_POST
def rider_reject_delivery_api(request, delivery_id):
    """Reject an assigned delivery job with a required reason."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    reason = payload.get('reason') or request.POST.get('reason') or ''

    try:
        DeliveryService.rider_reject_delivery(delivery, request.user, reason)
        messages.info(request, f"Assignment for Order {delivery.order.order_number} rejected.")
        return _action_response(request, "Delivery rejected.", 'delivery:rider_assignments')
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@rider_required
def rider_deliveries_view(request):
    """4.3 My Deliveries page with status filters and search."""
    status_filter = request.GET.get('status', '').upper()
    search_query = request.GET.get('q', '').strip()

    qs = Delivery.objects.filter(rider=request.user).select_related('order', 'zone')

    if status_filter in dict(Delivery.DeliveryStatus.choices):
        qs = qs.filter(status=status_filter)
    elif status_filter == 'ACTIVE':
        qs = qs.filter(status__in=['ASSIGNED', 'ACCEPTED', 'AWAITING_PICKUP', 'IN_TRANSIT'])

    if search_query:
        qs = qs.filter(
            Q(order__order_number__icontains=search_query)
            | Q(tracking_number__icontains=search_query)
            | Q(customer_name__icontains=search_query)
            | Q(delivery_address__icontains=search_query)
        )

    qs = qs.order_by('-updated_at')

    paginator = Paginator(qs, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    counts = {
        'all': Delivery.objects.filter(rider=request.user).count(),
        'assigned': Delivery.objects.filter(rider=request.user, status=Delivery.DeliveryStatus.ASSIGNED).count(),
        'accepted': Delivery.objects.filter(rider=request.user, status=Delivery.DeliveryStatus.ACCEPTED).count(),
        'in_transit': Delivery.objects.filter(rider=request.user, status=Delivery.DeliveryStatus.IN_TRANSIT).count(),
        'delivered': Delivery.objects.filter(rider=request.user, status=Delivery.DeliveryStatus.DELIVERED).count(),
        'failed': Delivery.objects.filter(rider=request.user, status=Delivery.DeliveryStatus.FAILED).count(),
    }

    context = {
        'deliveries': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'counts': counts,
    }
    return render(request, 'rider/deliveries.html', context)


@rider_required
def rider_delivery_detail_view(request, delivery_id):
    """4.4 Delivery Details page."""
    delivery = get_object_or_404(
        Delivery.objects.select_related('order', 'zone', 'rider').prefetch_related('order__items', 'history'),
        id=delivery_id,
        rider=request.user,
    )

    items = delivery.order.items.all()
    history = delivery.history.select_related('changed_by').order_by('-created_at')

    context = {
        'delivery': delivery,
        'order': delivery.order,
        'items': items,
        'history': history,
        'failure_reasons': Delivery.FailureReason.choices,
    }
    return render(request, 'rider/detail.html', context)


@rider_required
def rider_active_delivery_view(request):
    """4.5 Dedicated Active Delivery interface."""
    # Find current active delivery (prioritize IN_TRANSIT then ACCEPTED)
    active_delivery = Delivery.objects.filter(
        rider=request.user,
        status__in=[Delivery.DeliveryStatus.IN_TRANSIT, Delivery.DeliveryStatus.ACCEPTED],
    ).select_related('order', 'zone').order_by('-picked_up_at', '-accepted_at').first()

    context = {
        'delivery': active_delivery,
        'order': active_delivery.order if active_delivery else None,
        'failure_reasons': Delivery.FailureReason.choices,
    }
    return render(request, 'rider/active.html', context)


@rider_required
@require_POST
def rider_confirm_pickup_api(request, delivery_id):
    """Rider confirms pickup from shop; generates customer OTP."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    try:
        DeliveryService.confirm_pickup(delivery, request.user)
        messages.success(request, "Pickup confirmed! Package is now In Transit. Customer received OTP.")
        return _action_response(request, "Pickup confirmed and OTP dispatched to customer.", 'delivery:rider_active_delivery')
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@rider_required
@require_POST
def rider_verify_otp_api(request, delivery_id):
    """4.6 Proof of Delivery OTP Verification."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    otp_code = str(payload.get('otp') or payload.get('otp_code') or '').strip()
    recipient_name = str(payload.get('recipient_name') or '').strip()
    notes = str(payload.get('notes') or '').strip()

    if not otp_code:
        return _json_error("Please enter the 6-digit confirmation PIN provided by the customer.")

    try:
        result = DeliveryService.verify_delivery_otp(
            delivery=delivery,
            otp_candidate=otp_code,
            rider_user=request.user,
            recipient_name=recipient_name,
            notes=notes,
        )
        if isinstance(result, dict) and not result.get('success'):
            return _json_error(result['message'], status=400, errors={'attempts_remaining': result['attempts_remaining']})
        messages.success(request, f"Order {delivery.order.order_number} marked as Delivered! Great job!")
        return _action_response(request, "Delivery successfully confirmed and completed!", 'delivery:rider_history')
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@rider_required
@require_POST
def rider_report_failure_api(request, delivery_id):
    """4.7 Report delivery problem / failure."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    failure_reason = payload.get('failure_reason') or request.POST.get('failure_reason')
    failure_note = payload.get('failure_note') or request.POST.get('failure_note') or ''

    try:
        DeliveryService.report_delivery_failure(
            delivery=delivery,
            rider_user=request.user,
            failure_reason=failure_reason,
            failure_note=failure_note,
        )
        messages.warning(request, f"Delivery issue reported for Order {delivery.order.order_number}.")
        return _action_response(request, "Delivery failure reported to store management.", 'delivery:rider_deliveries')
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@rider_required
def rider_history_view(request):
    """4.8 Delivery History with filters and pagination."""
    qs = Delivery.objects.filter(
        rider=request.user,
        status__in=[Delivery.DeliveryStatus.DELIVERED, Delivery.DeliveryStatus.FAILED, Delivery.DeliveryStatus.RETURNED],
    ).select_related('order', 'zone').order_by('-delivered_at', '-updated_at')

    status_filter = request.GET.get('status', '').upper()
    if status_filter:
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'rider/history.html', {
        'deliveries': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
    })


@rider_required
def rider_profile_view(request):
    """4.9 Rider Profile viewing and approved field editing."""
    profile, _ = RiderProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        payload = _parse_payload(request)
        phone = (payload.get('phone_number') or '').strip()
        emergency_name = (payload.get('emergency_contact_name') or '').strip()
        emergency_phone = (payload.get('emergency_contact_phone') or '').strip()
        vehicle_type = payload.get('vehicle_type')
        vehicle_num = (payload.get('vehicle_number') or '').strip()
        address = (payload.get('address') or '').strip()

        if phone:
            profile.phone_number = phone
            request.user.phone_number = phone
            request.user.save(update_fields=['phone_number'])

        profile.emergency_contact_name = emergency_name
        profile.emergency_contact_phone = emergency_phone
        if vehicle_type in dict(RiderProfile.VehicleType.choices):
            profile.vehicle_type = vehicle_type
        profile.vehicle_number = vehicle_num
        profile.address = address
        profile.save()

        messages.success(request, "Profile updated successfully.")
        return redirect('delivery:rider_profile')

    return render(request, 'rider/profile.html', {
        'profile': profile,
        'rider': request.user,
        'vehicle_types': RiderProfile.VehicleType.choices,
    })


@rider_required
def rider_notifications_view(request):
    """4.10 Rider in-app Notifications."""
    from apps.notifications.models import Notification
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:30]
    return render(request, 'rider/notifications.html', {'notifications': notifications})


# ==============================================================================
# MANAGEMENT DELIVERY VIEWS
# ==============================================================================

@delivery_management_required
def management_delivery_dashboard_view(request):
    """5.1 Management Delivery Dashboard."""
    data = DeliveryService.get_management_dashboard_data()
    return render(request, 'delivery/dashboard.html', data)


@delivery_management_required
def management_all_deliveries_view(request):
    """5.2 All Deliveries with filters."""
    status_filter = request.GET.get('status', '').upper()
    search = request.GET.get('q', '').strip()
    rider_filter = request.GET.get('rider', '')

    qs = Delivery.objects.all().select_related('order', 'rider', 'zone').order_by('-created_at')

    if status_filter in dict(Delivery.DeliveryStatus.choices):
        qs = qs.filter(status=status_filter)
    elif status_filter == 'ACTIVE':
        qs = qs.filter(status__in=['ASSIGNED', 'ACCEPTED', 'AWAITING_PICKUP', 'IN_TRANSIT'])

    if rider_filter:
        qs = qs.filter(rider_id=rider_filter)

    if search:
        qs = qs.filter(
            Q(order__order_number__icontains=search)
            | Q(tracking_number__icontains=search)
            | Q(customer_name__icontains=search)
            | Q(delivery_address__icontains=search)
        )

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    riders = RiderProfile.objects.select_related('user').filter(user__is_active=True)

    context = {
        'deliveries': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'rider_filter': rider_filter,
        'riders': riders,
        'statuses': Delivery.DeliveryStatus.choices,
    }
    return render(request, 'delivery/list.html', context)


@delivery_management_required
def management_unassigned_deliveries_view(request):
    """5.3 Unassigned Deliveries queue."""
    qs = Delivery.objects.filter(
        status=Delivery.DeliveryStatus.PENDING_ASSIGNMENT
    ).select_related('order', 'zone').order_by('-created_at')

    riders = RiderProfile.objects.select_related('user').filter(user__is_active=True, is_available=True)
    return render(request, 'delivery/unassigned.html', {
        'deliveries': qs,
        'riders': riders,
    })


@delivery_management_required
def management_active_deliveries_view(request):
    """5.4 Active Deliveries in progress."""
    qs = Delivery.objects.filter(
        status__in=['ASSIGNED', 'ACCEPTED', 'AWAITING_PICKUP', 'IN_TRANSIT']
    ).select_related('order', 'rider', 'zone').order_by('-updated_at')

    return render(request, 'delivery/active.html', {'deliveries': qs})


@delivery_management_required
def management_completed_deliveries_view(request):
    """5.5 Completed Deliveries."""
    qs = Delivery.objects.filter(
        status=Delivery.DeliveryStatus.DELIVERED
    ).select_related('order', 'rider', 'zone').order_by('-delivered_at')

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'delivery/completed.html', {'deliveries': page_obj, 'page_obj': page_obj})


@delivery_management_required
def management_failed_deliveries_view(request):
    """5.6 Failed Deliveries."""
    qs = Delivery.objects.filter(
        status=Delivery.DeliveryStatus.FAILED
    ).select_related('order', 'rider', 'zone').order_by('-updated_at')

    riders = RiderProfile.objects.select_related('user').filter(user__is_active=True)
    return render(request, 'delivery/failed.html', {'deliveries': qs, 'riders': riders})


@delivery_management_required
def management_delivery_detail_view(request, delivery_id):
    """Management Delivery Details & Actions."""
    delivery = get_object_or_404(
        Delivery.objects.select_related('order', 'zone', 'rider').prefetch_related('order__items', 'history'),
        id=delivery_id,
    )

    items = delivery.order.items.all()
    history = delivery.history.select_related('changed_by').order_by('-created_at')
    riders = RiderProfile.objects.select_related('user').filter(user__is_active=True)

    context = {
        'delivery': delivery,
        'order': delivery.order,
        'items': items,
        'history': history,
        'riders': riders,
        'failure_reasons': Delivery.FailureReason.choices,
    }
    return render(request, 'delivery/detail.html', context)


@delivery_management_required
@require_POST
def management_assign_rider_api(request, delivery_id):
    """Assign or reassign rider from management portal."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    rider_id = payload.get('rider_id') or request.POST.get('rider_id')

    if not rider_id:
        return _json_error("Please select a rider.")

    try:
        rider_user = User.objects.get(id=rider_id, role='RIDER')
        DeliveryService.assign_rider(delivery, rider_user, assigned_by=request.user)
        messages.success(request, f"Rider {rider_user.get_full_name() or rider_user.username} assigned to Order {delivery.order.order_number}.")
        return _action_response(request, "Rider assigned successfully.")
    except User.DoesNotExist:
        return _json_error("Rider not found.", status=404)
    except ValidationError as e:
        msg = '; '.join(str(message) for message in e.messages)
        return _json_error(msg, status=400)


@delivery_management_required
@require_POST
def management_pod_override_api(request, delivery_id):
    """Management override for Proof of Delivery."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    reason = payload.get('reason') or request.POST.get('reason')
    recipient_name = payload.get('recipient_name') or request.POST.get('recipient_name') or ''
    notes = payload.get('notes') or request.POST.get('notes') or ''

    try:
        DeliveryService.management_override_pod(
            delivery=delivery,
            manager_user=request.user,
            reason=reason,
            recipient_name=recipient_name,
            notes=notes,
        )
        messages.success(request, f"Delivery for Order {delivery.order.order_number} marked as Delivered via Management Override.")
        return _json_response(message="POD override completed.")
    except (ValidationError, PermissionDenied) as e:
        msg = str(getattr(e, 'message', e))
        return _json_error(msg, status=400)


@delivery_management_required
@require_POST
def management_reschedule_api(request, delivery_id):
    """Reschedule delivery."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    rescheduled_date = payload.get('rescheduled_date') or request.POST.get('rescheduled_date')
    reason = payload.get('reason') or request.POST.get('reason') or ''

    if not rescheduled_date:
        return _json_error("New delivery date is required.")

    try:
        DeliveryService.reschedule_delivery(delivery, request.user, rescheduled_date, reason)
        messages.success(request, f"Delivery rescheduled to {rescheduled_date}.")
        return _json_response(message="Delivery rescheduled successfully.")
    except Exception as e:
        return _json_error(str(e), status=400)


@delivery_management_required
@require_POST
def management_return_api(request, delivery_id):
    """Mark package returned to store."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    reason = payload.get('reason') or request.POST.get('reason') or ''

    DeliveryService.return_delivery(delivery, request.user, reason)
    messages.info(request, f"Order {delivery.order.order_number} marked as Returned to Store.")
    return _json_response(message="Order marked as Returned.")


@delivery_management_required
@require_POST
def management_cancel_api(request, delivery_id):
    """Cancel delivery."""
    delivery = get_object_or_404(Delivery, id=delivery_id)
    payload = _parse_payload(request)
    reason = payload.get('reason') or request.POST.get('reason') or ''

    DeliveryService.cancel_delivery(delivery, request.user, reason)
    messages.warning(request, f"Delivery for Order {delivery.order.order_number} cancelled.")
    return _json_response(message="Delivery cancelled.")


@delivery_management_required
def management_riders_view(request):
    """5.7 Rider Management list and creation."""
    riders = RiderProfile.objects.select_related('user').all().order_by('-created_at')
    return render(request, 'delivery/riders.html', {
        'riders': riders,
        'vehicle_types': RiderProfile.VehicleType.choices,
        'fields': [('first_name', 'First name'), ('last_name', 'Last name'), ('email', 'Email'), ('username', 'Username'), ('phone_number', 'Phone'), ('password', 'Initial password')],
    })


@delivery_management_required
@require_POST
def management_create_rider_api(request):
    """Create new rider account."""
    payload = _parse_payload(request)
    try:
        user, profile = DeliveryService.create_rider_account(payload, created_by=request.user)
        messages.success(request, f"Rider account '{user.email}' created successfully.")
        return _action_response(request, "Rider account created.", 'delivery:management_riders')
    except ValidationError as e:
        msg = '; '.join(str(message) for message in e.messages)
        return _json_error(msg, status=400)


@delivery_management_required
def management_rider_detail_view(request, rider_id):
    """5.8 Rider Details page."""
    rider_user = get_object_or_404(User, id=rider_id, role='RIDER')
    profile, _ = RiderProfile.objects.get_or_create(user=rider_user)

    if request.method == 'POST':
        payload = _parse_payload(request)
        profile.phone_number = payload.get('phone_number') or profile.phone_number
        profile.vehicle_type = payload.get('vehicle_type') or profile.vehicle_type
        profile.vehicle_number = payload.get('vehicle_number') or profile.vehicle_number
        profile.license_number = payload.get('license_number') or profile.license_number
        profile.max_active_deliveries = int(payload.get('max_active_deliveries') or profile.max_active_deliveries)
        profile.notes = payload.get('notes', profile.notes)

        is_active = payload.get('is_active')
        if is_active is not None:
            rider_user.is_active = bool(is_active)
            rider_user.save(update_fields=['is_active'])

        profile.save()
        messages.success(request, "Rider details updated.")
        return redirect('delivery:management_rider_detail', rider_id=rider_id)

    assigned_deliveries = Delivery.objects.filter(rider=rider_user).select_related('order', 'zone').order_by('-created_at')[:20]

    return render(request, 'delivery/rider_detail.html', {
        'rider': rider_user,
        'profile': profile,
        'deliveries': assigned_deliveries,
        'vehicle_types': RiderProfile.VehicleType.choices,
    })


@delivery_management_required
@require_POST
def management_toggle_rider_status_api(request, rider_id):
    """Toggle rider active status."""
    rider_user = get_object_or_404(User, id=rider_id, role='RIDER')
    rider_user.is_active = not rider_user.is_active
    rider_user.save(update_fields=['is_active'])
    return _json_response(
        message=f"Rider account {'activated' if rider_user.is_active else 'deactivated'}.",
        data={'is_active': rider_user.is_active},
    )


@delivery_management_required
def management_zones_view(request):
    """5.9 Delivery Zones management."""
    if request.method == 'POST':
        payload = _parse_payload(request)
        name = (payload.get('name') or '').strip()
        code = (payload.get('code') or '').strip().upper()
        fee_raw = payload.get('fee') or '0.00'
        desc = payload.get('description', '').strip()
        eta = payload.get('estimated_delivery_time', '').strip()
        is_active = bool(payload.get('is_active', True))

        if not name:
            messages.error(request, "Zone name is required.")
        else:
            try:
                fee = Decimal(fee_raw)
                if not code:
                    code = ''.join(char for char in name.upper() if char.isalnum())[:10] or f'ZONE{timezone.now():%H%M%S}'
                DeliveryZone.objects.create(
                    name=name,
                    code=code,
                    fee=fee,
                    description=desc,
                    estimated_delivery_time=eta or '30-60 mins',
                    is_active=is_active,
                )
                messages.success(request, f"Zone '{name}' created successfully.")
            except Exception as e:
                messages.error(request, f"Failed to create zone: {e}")
        return redirect('delivery:management_zones')

    zones = DeliveryZone.objects.all().order_by('name')
    return render(request, 'delivery/zones.html', {'zones': zones})


@delivery_management_required
@require_POST
def management_zone_toggle_api(request, zone_id):
    """Toggle zone active status."""
    zone = get_object_or_404(DeliveryZone, id=zone_id)
    zone.is_active = not zone.is_active
    zone.save(update_fields=['is_active', 'updated_at'])
    return _action_response(request, f"Zone '{zone.name}' {'activated' if zone.is_active else 'deactivated'}.", 'delivery:management_zones')


@delivery_management_required
def management_settings_view(request):
    """5.10 Delivery Settings."""
    settings_obj = DeliverySetting.get_settings()

    if request.method == 'POST':
        payload = _parse_payload(request)
        settings_obj.otp_expiry_minutes = int(payload.get('otp_expiry_minutes') or 60)
        settings_obj.max_otp_attempts = int(payload.get('max_otp_attempts') or 5)
        settings_obj.allow_management_override = _as_bool(payload.get('allow_management_override'))
        settings_obj.auto_assign_enabled = _as_bool(payload.get('auto_assign_enabled'))
        settings_obj.max_active_deliveries_per_rider = int(payload.get('max_active_deliveries_per_rider') or 4)
        settings_obj.support_phone = payload.get('support_phone', settings_obj.support_phone)
        settings_obj.save()

        messages.success(request, "Delivery settings saved successfully.")
        return redirect('delivery:management_settings')

    return render(request, 'delivery/settings.html', {'settings': settings_obj})


@delivery_management_required
def management_reports_view(request):
    """5.11 Delivery Reports & Metrics."""
    all_deliveries = Delivery.objects.all()
    total = all_deliveries.count()
    completed = all_deliveries.filter(status=Delivery.DeliveryStatus.DELIVERED).count()
    failed = all_deliveries.filter(status=Delivery.DeliveryStatus.FAILED).count()
    returned = all_deliveries.filter(status=Delivery.DeliveryStatus.RETURNED).count()

    success_rate = (completed / total * 100) if total > 0 else 0.0

    failure_reasons = (
        all_deliveries.filter(status=Delivery.DeliveryStatus.FAILED)
        .values('failure_reason')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    rider_stats = (
        User.objects.filter(role='RIDER')
        .annotate(
            total_jobs=Count('assigned_deliveries'),
            delivered_jobs=Count('assigned_deliveries', filter=Q(assigned_deliveries__status=Delivery.DeliveryStatus.DELIVERED)),
            failed_jobs=Count('assigned_deliveries', filter=Q(assigned_deliveries__status=Delivery.DeliveryStatus.FAILED)),
        )
        .select_related('rider_profile')
    )

    context = {
        'total': total,
        'completed': completed,
        'failed': failed,
        'returned': returned,
        'success_rate': round(success_rate, 1),
        'failure_reasons': failure_reasons,
        'rider_stats': rider_stats,
    }
    return render(request, 'delivery/reports.html', context)


# ==============================================================================
# CUSTOMER & PUBLIC API ENDPOINTS
# ==============================================================================

def public_delivery_zones_api(request):
    """Public API for active delivery zones and fees for checkout calculation."""
    zones = DeliveryZone.objects.filter(is_active=True).order_by('name')
    data = [
        {
            'id': z.id,
            'name': z.name,
            'code': z.code,
            'fee': str(z.fee),
            'estimated_delivery_time': z.estimated_delivery_time,
            'description': z.description,
        }
        for z in zones
    ]
    return _json_response(data=data, message="Delivery zones retrieved.")


def customer_delivery_tracking_api(request, order_ref):
    """
    Customer Delivery Tracking API.
    Enforces customer isolation: user must be authenticated and own the order (or be staff).
    Returns real delivery status, rider contact (safe), progress timeline, and doorstep instructions.
    """
    if not request.user or not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401)

    # Lookup order by order_number or id
    order = Order.objects.filter(
        Q(order_number__iexact=order_ref) | Q(id=order_ref if str(order_ref).isdigit() else -1)
    ).first()

    if not order:
        return _json_error("Order not found.", status=404)

    # Customer isolation
    if request.user.role == 'CUSTOMER' and order.customer != request.user:
        return _json_error("Unauthorized to track this order.", status=403)

    delivery = getattr(order, 'delivery', None)
    if not delivery:
        return _json_response(
            data={'has_delivery': False, 'order_status': order.status},
            message="No delivery record found for this order.",
        )

    rider_info = None
    if delivery.rider:
        profile = getattr(delivery.rider, 'rider_profile', None)
        rider_info = {
            'name': delivery.rider.get_full_name() or 'Assigned Rider',
            'phone': getattr(delivery.rider, 'phone_number', '') or '',
            'vehicle': profile.get_vehicle_type_display() if profile else 'Courier',
        }

    return _json_response(
        data={
            'has_delivery': True,
            'tracking_number': delivery.tracking_number,
            'status': delivery.status,
            'status_display': delivery.get_status_display(),
            'customer_name': delivery.customer_name,
            'delivery_address': delivery.delivery_address,
            'assigned_at': delivery.assigned_at.isoformat() if delivery.assigned_at else None,
            'picked_up_at': delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
            'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            'rider': rider_info,
            'pod_method': delivery.pod_method if delivery.is_delivered else None,
            'is_delivered': delivery.is_delivered,
            'is_failed': delivery.is_failed,
        },
        message="Delivery tracking status retrieved.",
    )
