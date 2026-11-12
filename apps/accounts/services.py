"""
Authentication and role redirection services for MADAM HY Smart Shop.
"""
from django.urls import NoReverseMatch, reverse


def get_role_redirect_url(user):
    """
    Intelligent role-aware landing and post-login redirection resolver.
    Directs users immediately to their designated interface:
      - Anonymous / Guest: /customer/products/
      - CUSTOMER: /customer/products/
      - CASHIER: /sales/pos/
      - MANAGER: /reports/ (or /inventory/)
      - OWNER / ADMIN: /reports/ (Dashboard)
    """
    if not user or not getattr(user, 'is_authenticated', False):
        try:
            return reverse('customer_orders:products')
        except NoReverseMatch:
            try:
                return reverse('products:customer_products')
            except NoReverseMatch:
                return '/customer/products/'

    role = (getattr(user, 'role', '') or '').upper()

    if role in ['OWNER', 'ADMIN'] or getattr(user, 'is_superuser', False):
        try:
            return reverse('reports:report_dashboard')
        except NoReverseMatch:
            try:
                return reverse('reports:reports_dashboard')
            except NoReverseMatch:
                return '/reports/'
    elif role == 'MANAGER':
        try:
            return reverse('reports:report_dashboard')
        except NoReverseMatch:
            try:
                return reverse('reports:reports_dashboard')
            except NoReverseMatch:
                return '/reports/'
    elif role == 'CASHIER':
        try:
            return reverse('sales:pos')
        except NoReverseMatch:
            return '/sales/pos/'
    elif role == 'RIDER':
        try:
            return reverse('delivery:rider_dashboard')
        except NoReverseMatch:
            return '/rider/'
    elif role == 'CUSTOMER':
        try:
            return reverse('customer_orders:products')
        except NoReverseMatch:
            try:
                return reverse('products:customer_products')
            except NoReverseMatch:
                return '/customer/products/'

    # Default fallback for authenticated users
    try:
        return reverse('customer_orders:products')
    except NoReverseMatch:
        try:
            return reverse('products:customer_products')
        except NoReverseMatch:
            return '/customer/products/'
