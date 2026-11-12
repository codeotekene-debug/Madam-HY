import json
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


def _json_response(data=None, message='Success', success=True, status=200, errors=None, **extra):
    """Consistent JSON response helper supporting root-level and nested data."""
    payload = {'success': success, 'message': message}
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    for k, v in extra.items():
        payload[k] = v
    response = JsonResponse(payload, status=status)
    if data is not None and isinstance(data, dict):
        response.context = {**payload, **data}
    elif data is not None:
        response.context = payload
    return response


def _is_authenticated(user):
    """Check if the requesting user is authenticated."""
    return bool(user and getattr(user, 'is_authenticated', False))


def _wants_json(request):
    """Strict content negotiation: check if caller requests JSON or HTML."""
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


def _parse_is_read_filter(val):
    """Parse is_read query param into True, False, or None."""
    if val is None:
        return None
    val_str = str(val).strip().lower()
    if val_str in ('true', '1', 'read'):
        return True
    if val_str in ('false', '0', 'unread'):
        return False
    return None


def notification_inbox(request):
    """User notifications inbox: supports filtering, pagination, HTML UI, and JSON API."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(
                message='Authentication required.',
                success=False,
                status=401,
            )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    # Query filters
    is_read_param = request.GET.get('is_read')
    status_param = request.GET.get('status')
    filter_is_read = _parse_is_read_filter(is_read_param if is_read_param is not None else status_param)

    raw_type = request.GET.get('type') or request.GET.get('notification_type') or ''
    filter_type = raw_type.strip().upper() if raw_type.strip().upper() in Notification.NotificationType.values else ''

    raw_priority = request.GET.get('priority') or ''
    filter_priority = raw_priority.strip().upper() if raw_priority.strip().upper() in Notification.Priority.values else ''

    search_query = (request.GET.get('q') or request.GET.get('search') or '').strip()

    # Query queryset
    notifications_qs = NotificationService.get_user_notifications(
        user=request.user,
        is_read=filter_is_read,
        notification_type=filter_type or None,
        priority=filter_priority or None,
        search=search_query or None,
    )

    # Metrics
    metrics = NotificationService.get_notification_metrics(request.user)

    # Pagination
    page_size = request.GET.get('page_size') or request.GET.get('per_page') or 15
    try:
        page_size = min(max(int(page_size), 1), 100)
    except (ValueError, TypeError):
        page_size = 15

    paginator = Paginator(notifications_qs, page_size)
    page_number = request.GET.get('page') or 1
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    if _wants_json(request):
        serialized_items = [NotificationService.serialize_notification(n) for n in page_obj]
        pagination = {
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'per_page': page_size,
        }
        return _json_response(
            data={
                'notifications': serialized_items,
                'pagination': pagination,
                'metrics': metrics,
            },
            unread_count=metrics['unread'],
            message='Notifications retrieved successfully.',
        )

    context = {
        'notifications': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'metrics': metrics,
        'unread_count': metrics['unread'],
        'filter_is_read': request.GET.get('is_read') or request.GET.get('status') or '',
        'filter_type': filter_type,
        'filter_priority': filter_priority,
        'search_query': search_query,
        'notification_types': Notification.NotificationType.choices,
        'priority_choices': Notification.Priority.choices,
        'notifications_json': json.dumps([NotificationService.serialize_notification(n) for n in page_obj]),
        'active_module': 'notifications',
        'active_tab': 'unread' if filter_is_read is False else ('settings' if request.GET.get('tab') == 'settings' else 'all'),
    }
    return render(request, 'notifications/notifications.html', context)


def unread_count_api(request):
    """Fast, lightweight endpoint returning unread count for navbar badge updates."""
    if not _is_authenticated(request.user):
        return _json_response(
            data={'unread_count': 0},
            unread_count=0,
            message='Authentication required.',
            success=False,
            status=401,
        )

    count = NotificationService.get_unread_count(request.user)
    return _json_response(
        data={'unread_count': count},
        unread_count=count,
        message='Unread count retrieved.',
        status=200,
    )


def mark_notification_read(request, id):
    """Mark an individual notification as read. Enforces user isolation."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(
                message='Authentication required.',
                success=False,
                status=401,
            )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    if request.method != 'POST':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Use POST.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['POST'])

    try:
        notif_pk = int(id)
    except (ValueError, TypeError):
        return _json_response(
            message='Invalid notification ID format.',
            success=False,
            status=400,
        )

    notification = Notification.objects.filter(pk=notif_pk).first()
    if not notification:
        return _json_response(
            message='Notification not found.',
            success=False,
            status=404,
        )

    if notification.recipient != request.user:
        return _json_response(
            message='Permission denied. You cannot modify notifications belonging to another user.',
            success=False,
            status=403,
        )

    notification.mark_as_read()
    new_unread_count = NotificationService.get_unread_count(request.user)

    if _wants_json(request):
        return _json_response(
            data={
                'notification': NotificationService.serialize_notification(notification),
                'unread_count': new_unread_count,
            },
            unread_count=new_unread_count,
            message='Notification marked as read.',
            status=200,
        )

    messages.success(request, 'Notification marked as read.')
    return redirect('notifications:inbox')


def mark_notification_unread(request, id):
    """Mark an individual notification as unread. Enforces user isolation."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(
                message='Authentication required.',
                success=False,
                status=401,
            )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    if request.method != 'POST':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Use POST.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['POST'])

    try:
        notif_pk = int(id)
    except (ValueError, TypeError):
        return _json_response(
            message='Invalid notification ID format.',
            success=False,
            status=400,
        )

    notification = Notification.objects.filter(pk=notif_pk).first()
    if not notification:
        return _json_response(
            message='Notification not found.',
            success=False,
            status=404,
        )

    if notification.recipient != request.user:
        return _json_response(
            message='Permission denied. You cannot modify notifications belonging to another user.',
            success=False,
            status=403,
        )

    notification.mark_as_unread()
    new_unread_count = NotificationService.get_unread_count(request.user)

    if _wants_json(request):
        return _json_response(
            data={
                'notification': NotificationService.serialize_notification(notification),
                'unread_count': new_unread_count,
            },
            unread_count=new_unread_count,
            message='Notification marked as unread.',
            status=200,
        )

    messages.success(request, 'Notification marked as unread.')
    return redirect('notifications:inbox')


def mark_all_read(request):
    """Bulk mark all unread notifications as read for authenticated user."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(
                message='Authentication required.',
                success=False,
                status=401,
            )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    if request.method != 'POST':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Use POST.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['POST'])

    updated_count = NotificationService.mark_all_as_read(request.user)

    if _wants_json(request):
        return _json_response(
            data={
                'marked_count': updated_count,
                'unread_count': 0,
            },
            unread_count=0,
            message=f'All {updated_count} notifications marked as read.',
            status=200,
        )

    messages.success(request, f'Marked {updated_count} notifications as read.')
    return redirect('notifications:inbox')
