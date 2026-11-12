import json
from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import ActivityLogService

MANAGEMENT_ROLES = {'OWNER', 'MANAGER'}


def _json_response(data=None, message='Success', success=True, status=200, errors=None, **extra):
    """Consistent JSON response utility supporting root-level and nested payloads."""
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
    """Check if the user is authenticated."""
    return bool(user and getattr(user, 'is_authenticated', False))


def _wants_json(request):
    """Strict content negotiation: check if caller requested JSON format."""
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


def _check_management_permission(request):
    """Verify user is authenticated and possesses OWNER or MANAGER role."""
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(
                message='Authentication required.',
                success=False,
                status=401,
            )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    if request.user.role not in MANAGEMENT_ROLES:
        return _json_response(
            message='Permission denied. Activity logs are restricted to Owner and Manager roles.',
            success=False,
            status=403,
        )
    return None


def activity_log_list(request):
    """Audit Log List View: paginated, searchable, filterable management audit trail."""
    auth_check = _check_management_permission(request)
    if auth_check:
        return auth_check

    if request.method != 'GET':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Activity logs are strictly read-only.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['GET'])

    action_param = request.GET.get('action') or request.GET.get('action_type') or ''
    actor_param = request.GET.get('actor_id') or request.GET.get('actor') or ''
    entity_param = request.GET.get('entity') or request.GET.get('model') or ''
    start_date_param = request.GET.get('start_date') or ''
    end_date_param = request.GET.get('end_date') or ''
    search_param = (request.GET.get('q') or request.GET.get('search') or '').strip()

    logs_qs = ActivityLogService.get_activity_logs(
        action=action_param or None,
        actor_id=actor_param or None,
        entity=entity_param or None,
        start_date=start_date_param or None,
        end_date=end_date_param or None,
        search=search_param or None,
    )

    metrics = ActivityLogService.get_activity_metrics()

    # Pagination
    page_size = request.GET.get('page_size') or request.GET.get('per_page') or 20
    try:
        page_size = min(max(int(page_size), 1), 100)
    except (ValueError, TypeError):
        page_size = 20

    paginator = Paginator(logs_qs, page_size)
    page_number = request.GET.get('page') or 1
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    if _wants_json(request):
        serialized_logs = [ActivityLogService.serialize_activity_log(item) for item in page_obj]
        pagination = {
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,
            'per_page': page_size,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
        return _json_response(
            data={
                'logs': serialized_logs,
                'pagination': pagination,
                'metrics': metrics,
            },
            message='Activity logs retrieved successfully.',
        )

    context = {
        'logs': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'metrics': metrics,
        'action_choices': ActivityLog.ActionType.choices,
        'available_entities': metrics['available_entities'],
        'filter_action': action_param,
        'filter_actor': actor_param,
        'filter_entity': entity_param,
        'filter_start_date': start_date_param,
        'filter_end_date': end_date_param,
        'search_query': search_param,
        'logs_json': json.dumps([ActivityLogService.serialize_activity_log(item) for item in page_obj]),
    }
    return render(request, 'activity_logs/activity_logs.html', context)


def activity_log_detail(request, id):
    """Audit Log Detail View: detailed inspection of state diffs, telemetry, and metadata."""
    auth_check = _check_management_permission(request)
    if auth_check:
        return auth_check

    if request.method != 'GET':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Activity logs are strictly read-only.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['GET'])

    log = ActivityLog.objects.select_related('actor', 'content_type').filter(pk=id).first()
    if not log:
        return _json_response(
            message='Activity log entry not found.',
            success=False,
            status=404,
        )

    serialized = ActivityLogService.serialize_activity_log(log)

    if _wants_json(request):
        return _json_response(
            data=serialized,
            message='Activity log details retrieved.',
        )

    context = {
        'log': log,
        'serialized': serialized,
        'metadata_json': json.dumps(log.metadata, indent=2) if log.metadata else '{}',
        'changes_diff': log.changes_diff,
    }
    return render(request, 'activity_logs/log_detail.html', context)


def activity_log_metrics(request):
    """Summary Metrics API endpoint returning audit log activity counts and statistics."""
    auth_check = _check_management_permission(request)
    if auth_check:
        return auth_check

    if request.method != 'GET':
        if _wants_json(request):
            return _json_response(
                message='Method not allowed. Activity logs are strictly read-only.',
                success=False,
                status=405,
            )
        return HttpResponseNotAllowed(['GET'])

    metrics = ActivityLogService.get_activity_metrics()
    return _json_response(
        data=metrics,
        message='Activity log metrics retrieved.',
    )
