from functools import wraps
from django.shortcuts import redirect, render
from django.urls import reverse
from django.http import JsonResponse


def _request_wants_json(request):
    format_param = (request.GET.get('format') or '').lower()
    if format_param == 'json':
        return True
    if format_param == 'html':
        return False
    accept_header = request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')
    if 'text/html' in accept_header and 'application/json' not in accept_header:
        return False
    if 'application/json' in accept_header and 'text/html' not in accept_header:
        return True
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    return True


def role_required(*allowed_roles):
    """
    Decorator for views that checks whether the user is authenticated and has
    one of the specified roles.

    - Unauthenticated: redirects to login (HTML) or returns 401 (JSON).
    - Authenticated with wrong role (e.g. CASHIER accessing OWNER-only): returns HTTP 403.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                if _request_wants_json(request):
                    return JsonResponse(
                        {'success': False, 'message': 'Authentication required.'},
                        status=401,
                    )
                return redirect(f"{reverse('accounts:login')}?next={request.path}")

            user_role = getattr(request.user, 'role', None)
            if user_role not in allowed_roles:
                if _request_wants_json(request):
                    return JsonResponse(
                        {'success': False, 'message': 'You do not have permission to access this resource.'},
                        status=403,
                    )
                return render(
                    request,
                    '403.html',
                    {'message': 'You do not have permission to access this resource.'},
                    status=403,
                )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
