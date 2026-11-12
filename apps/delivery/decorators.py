from functools import wraps
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse


def _wants_json(request):
    format_param = (request.GET.get('format') or '').lower()
    if format_param == 'json':
        return True
    accept_header = request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')
    if 'application/json' in accept_header and 'text/html' not in accept_header:
        return True
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    return False


def rider_required(view_func):
    """
    Decorator requiring an authenticated user with the RIDER role.
    Unauthenticated -> redirects to login or 401 JSON.
    Non-rider -> 403.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            if _wants_json(request):
                return JsonResponse({'success': False, 'message': 'Authentication required.'}, status=401)
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if getattr(request.user, 'role', None) != 'RIDER':
            if _wants_json(request):
                return JsonResponse({'success': False, 'message': 'Rider role required.'}, status=403)
            return render(request, '403.html', {'message': 'Rider portal access restricted to approved delivery riders.'}, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped


def delivery_management_required(view_func):
    """
    Decorator requiring OWNER, MANAGER, or STAFF permissions.
    """
    allowed_roles = {'OWNER', 'MANAGER', 'STAFF'}

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            if _wants_json(request):
                return JsonResponse({'success': False, 'message': 'Authentication required.'}, status=401)
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        if getattr(request.user, 'role', None) not in allowed_roles:
            if _wants_json(request):
                return JsonResponse({'success': False, 'message': 'Management authorization required.'}, status=403)
            return render(request, '403.html', {'message': 'Delivery management restricted to store owners, managers, and authorized staff.'}, status=403)

        return view_func(request, *args, **kwargs)
    return _wrapped
