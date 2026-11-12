"""Custom HTTP error handlers for MADAM HY Smart Shop.

Provides dual HTML/JSON error responses, brand-tailored error presentation,
and safe contextual recovery paths.
"""
from django.http import JsonResponse
from django.shortcuts import redirect, render


def root_entry_view(request):
    """
    Intelligent role-aware landing entry point for root '/'.
    Directs users immediately to their designated interface based on role:
      - Anonymous / Guest: /customer/products/
      - CUSTOMER: /customer/products/
      - CASHIER: /sales/pos/
      - MANAGER: /reports/ (or /inventory/)
      - OWNER / ADMIN: /reports/ (Dashboard)
    """
    from apps.accounts.services import get_role_redirect_url
    target_url = get_role_redirect_url(request.user)
    return redirect(target_url)


def _wants_json(request):
    """Check if the client preferred a JSON error payload."""
    format_param = (request.GET.get('format') or '').lower()
    if format_param == 'json':
        return True
    if format_param == 'html':
        return False
    accept = request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    return False


def custom_403_view(request, exception=None):
    """Custom 403 Forbidden handler with role-gated return paths."""
    if _wants_json(request):
        return JsonResponse({
            'success': False,
            'message': 'Access forbidden. You do not have permission to view or perform operations on this resource.',
            'status_code': 403,
            'error': str(exception) if exception else 'Forbidden',
        }, status=403)
    return render(request, '403.html', {'exception': exception}, status=403)


def custom_404_view(request, exception=None):
    """Custom 404 Not Found handler."""
    if _wants_json(request):
        return JsonResponse({
            'success': False,
            'message': 'Resource not found. The requested endpoint or record does not exist.',
            'status_code': 404,
            'error': str(exception) if exception else 'Not Found',
        }, status=404)
    return render(request, '404.html', {'exception': exception}, status=404)


def custom_500_view(request):
    """Custom 500 Server Error handler."""
    if _wants_json(request):
        return JsonResponse({
            'success': False,
            'message': 'An unexpected server error occurred. Our technical staff has been alerted.',
            'status_code': 500,
        }, status=500)
    return render(request, '500.html', status=500)
