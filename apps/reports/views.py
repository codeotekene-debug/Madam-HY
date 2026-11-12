from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.expenses.models import Expense

from .services import (
    credit_summary,
    expense_report,
    get_date_range,
    growth_report,
    inventory_summary,
    profit_report,
    sales_report,
)

User = get_user_model()
REPORT_ALLOWED_ROLES = ('OWNER', 'MANAGER')


def _is_authenticated(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def _wants_json(request):
    format_param = (request.GET.get('format') or '').lower().strip()
    if format_param == 'json':
        return True
    if format_param == 'html':
        return False
    accept = request.headers.get('accept', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    return False


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
    payload = {'success': success, 'message': message}
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    response = JsonResponse(payload, status=status, encoder=DjangoJSONEncoder)
    if data is not None and isinstance(data, dict):
        response.context = {**payload, **data}
    elif data is not None:
        response.context = payload
    return response


def _check_reports_permission(request):
    """
    Ensure user is authenticated and has OWNER or MANAGER role.
    Returns (authorized: bool, response: HttpResponse | None).
    """
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return False, _json_response(message='Authentication required.', success=False, status=401)
        return False, redirect('accounts:login')

    user_role = getattr(request.user, 'role', None)
    if user_role not in REPORT_ALLOWED_ROLES:
        return False, _json_response(
            message='Access denied. Only Owners and Managers can access reports.',
            success=False,
            status=403,
        )
    return True, None


def _parse_period_and_dates(request):
    period = request.GET.get('period', 'this_month')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    return period, start_date, end_date


def _log_report_view(request, report_label, description, metadata=None):
    try:
        log_activity(
            actor=request.user,
            action_type=ActivityLog.ActionType.VIEWED,
            action_label=report_label,
            description=description,
            metadata=metadata or {},
        )
    except Exception:
        pass


def _build_revenue_chart(sales_data):
    """Build a completed-sale revenue series for the selected report interval."""
    start_date = sales_data['start_date']
    end_date = sales_data['end_date']
    monthly = (end_date - start_date).days + 1 > 31
    totals = {}
    for row in sales_data['sales_by_day']:
        day = row['day']
        key = day.strftime('%Y-%m') if monthly else day.isoformat()
        totals[key] = totals.get(key, Decimal('0.00')) + row['total_sales']

    points = []
    cursor = start_date.replace(day=1) if monthly else start_date
    last_bucket = end_date.replace(day=1) if monthly else end_date
    while cursor <= last_bucket:
        key = cursor.strftime('%Y-%m') if monthly else cursor.isoformat()
        points.append({
            'label': cursor.strftime('%b %Y') if monthly else cursor.strftime('%d %b'),
            'date': key,
            'revenue': totals.get(key, Decimal('0.00')),
        })
        if monthly:
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cursor += timedelta(days=1)

    maximum = max((point['revenue'] for point in points), default=Decimal('0.00'))
    for point in points:
        point['bar_percent'] = (
            float(point['revenue'] / maximum * Decimal('100')) if maximum else 0
        )
    return points


# ==============================================================================
# Views
# ==============================================================================


def reports_dashboard(request):
    """
    Main Reports Dashboard (GET /reports/).
    Overview metrics: today's revenue, net profit, monthly expenses, low stock alert summary.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    authorized, error_response = _check_reports_permission(request)
    if not authorized:
        return error_response

    period, start_date, end_date = _parse_period_and_dates(request)
    try:
        # High-level overview card metrics
        today_sales = sales_report(period='today')
        today_profit = profit_report(period='today')
        month_expenses = expense_report(period='this_month', status=Expense.Status.APPROVED)
        inv_summary = inventory_summary()
        crd_summary = credit_summary(period='this_month')

        # Selected period reports
        p_sales = sales_report(period=period, start_date=start_date, end_date=end_date)
        p_expenses = expense_report(period=period, start_date=start_date, end_date=end_date, status=Expense.Status.APPROVED)
        p_profit = profit_report(period=period, start_date=start_date, end_date=end_date)
        p_growth = growth_report(period=period, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        if _wants_json(request):
            return _json_response(message=str(exc), success=False, status=400, errors={'filter': str(exc)})
        return render(request, 'reports/reports.html', {
            'error': str(exc),
            'period': period,
            'overview_data': {},
            'growth_report': {},
            'revenue_chart': [],
        }, status=400)

    # Calculate key highlights
    top_cat = p_sales['sales_by_category'][0]['category'] if p_sales['sales_by_category'] else 'None'
    exp_ratio = Decimal('0.00')
    if p_sales['total_sales'] > 0:
        exp_ratio = ((p_expenses['total_expenses'] / p_sales['total_sales']) * Decimal('100')).quantize(Decimal('0.01'))

    overview_metrics = {
        'today_revenue': today_sales['total_sales'],
        'today_net_profit': today_profit['net_profit'],
        'monthly_expenses': month_expenses['total_expenses'],
        'low_stock_products': inv_summary['low_stock_products'],
        'out_of_stock_products': inv_summary['out_of_stock_products'],
        'total_products': inv_summary['total_products'],
        'total_sales': p_sales['total_sales'],
        'total_expenses': p_expenses['total_expenses'],
        'gross_profit': p_profit['gross_profit'],
        'net_profit': p_profit['net_profit'],
        'transactions': p_sales['sales_count'],
        'aov': p_sales['average_sale'],
        'comparison': p_growth['sales_growth_percentage'],
        'top_category': top_cat,
        'expense_ratio': exp_ratio,
        'profit_margin': p_profit['profit_margin'],
        'customer_growth': p_growth['sales_volume_growth_percentage'],
    }

    _log_report_view(
        request,
        report_label='Viewed Reports Dashboard',
        description=f'User {request.user.email} viewed Reports Dashboard for period {period}.',
        metadata={
            'period': period,
            'start_date': str(p_sales['start_date']),
            'end_date': str(p_sales['end_date']),
        },
    )

    data = {
        'overview': {
            'today_revenue': overview_metrics['today_revenue'],
            'today_net_profit': overview_metrics['today_net_profit'],
            'monthly_expenses': overview_metrics['monthly_expenses'],
            'low_stock_products': overview_metrics['low_stock_products'],
            'out_of_stock_products': overview_metrics['out_of_stock_products'],
            'total_products': overview_metrics['total_products'],
        },
        'period': period,
        'start_date': p_sales['start_date'],
        'end_date': p_sales['end_date'],
        'sales': p_sales,
        'expenses': p_expenses,
        'profit': p_profit,
        'growth': p_growth,
        'inventory': inv_summary,
        'credits': crd_summary,
    }

    if _wants_json(request):
        return _json_response(data=data, message='Reports dashboard retrieved successfully.')

    context = {
        'overview_data': overview_metrics,
        'period': period,
        'start_date': p_sales['start_date'],
        'end_date': p_sales['end_date'],
        'sales_report': p_sales,
        'expense_report': p_expenses,
        'profit_report': p_profit,
        'growth_report': p_growth,
        'revenue_chart': _build_revenue_chart(p_sales),
        'inventory_summary': inv_summary,
        'credit_summary': crd_summary,
    }
    return render(request, 'reports/reports.html', context)


def sales_report_view(request):
    """
    Sales Report (GET /reports/sales/).
    Detailed breakdown of sales by date range, payment method distribution, and top-selling products.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    authorized, error_response = _check_reports_permission(request)
    if not authorized:
        return error_response

    period, start_date, end_date = _parse_period_and_dates(request)
    payment_method = request.GET.get('payment_method')

    try:
        report_data = sales_report(period=period, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        if _wants_json(request):
            return _json_response(message=str(exc), success=False, status=400, errors={'filter': str(exc)})
        return render(request, 'reports/sales_report.html', {'error': str(exc)}, status=400)

    # Optional payment method filtering on distribution
    if payment_method and payment_method.lower() != 'all':
        norm_method = payment_method.upper().strip()
        filtered_methods = [
            item for item in report_data['sales_by_payment_method']
            if item['payment_method'].upper() == norm_method
        ]
        report_data['filtered_payment_methods'] = filtered_methods

    _log_report_view(
        request,
        report_label='Viewed Sales Report',
        description=f'User {request.user.email} viewed Sales Report for period {period}.',
        metadata={
            'period': period,
            'start_date': str(report_data['start_date']),
            'end_date': str(report_data['end_date']),
            'total_sales': str(report_data['total_sales']),
        },
    )

    if _wants_json(request):
        return _json_response(data=report_data, message='Sales report retrieved successfully.')

    context = {
        'sales_data': report_data,
        'period': period,
        'start_date': report_data['start_date'],
        'end_date': report_data['end_date'],
        'payment_method': payment_method or 'all',
    }
    return render(request, 'reports/sales_report.html', context)


def expense_report_view(request):
    """
    Expense Report (GET /reports/expenses/).
    Category-wise breakdown of approved expenses, vendor summary, and trends.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    authorized, error_response = _check_reports_permission(request)
    if not authorized:
        return error_response

    period, start_date, end_date = _parse_period_and_dates(request)
    category = request.GET.get('category')

    try:
        report_data = expense_report(period=period, start_date=start_date, end_date=end_date, status=Expense.Status.APPROVED)
    except ValueError as exc:
        if _wants_json(request):
            return _json_response(message=str(exc), success=False, status=400, errors={'filter': str(exc)})
        return render(request, 'reports/expense_report.html', {'error': str(exc)}, status=400)

    if category and category.lower() != 'all':
        norm_cat = category.upper().strip()
        report_data['recent_expenses'] = [
            item for item in report_data['recent_expenses']
            if item['category'].upper() == norm_cat
        ]

    # Calculate top category and average
    top_category = report_data['expenses_by_category'][0]['category'] if report_data['expenses_by_category'] else 'None'
    monthly_avg = report_data['total_expenses']

    _log_report_view(
        request,
        report_label='Viewed Expense Report',
        description=f'User {request.user.email} viewed Expense Report for period {period}.',
        metadata={
            'period': period,
            'start_date': str(report_data['start_date']),
            'end_date': str(report_data['end_date']),
            'total_expenses': str(report_data['total_expenses']),
        },
    )

    if _wants_json(request):
        return _json_response(data=report_data, message='Expense report retrieved successfully.')

    context = {
        'expense_data': report_data,
        'top_category': top_category,
        'monthly_average': monthly_avg,
        'period': period,
        'start_date': report_data['start_date'],
        'end_date': report_data['end_date'],
        'category': category or 'all',
    }
    return render(request, 'reports/expense_report.html', context)


def profit_report_view(request):
    """
    Profit & Loss Report (GET /reports/profit/).
    Net profit calculations (Gross Sales - COGS - Approved Expenses).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    authorized, error_response = _check_reports_permission(request)
    if not authorized:
        return error_response

    period, start_date, end_date = _parse_period_and_dates(request)
    try:
        report_data = profit_report(period=period, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        if _wants_json(request):
            return _json_response(message=str(exc), success=False, status=400, errors={'filter': str(exc)})
        return render(request, 'reports/profit_report.html', {'error': str(exc)}, status=400)

    _log_report_view(
        request,
        report_label='Viewed Profit Report',
        description=f'User {request.user.email} viewed Profit Report for period {period}.',
        metadata={
            'period': period,
            'start_date': str(report_data['start_date']),
            'end_date': str(report_data['end_date']),
            'net_profit': str(report_data['net_profit']),
        },
    )

    if _wants_json(request):
        return _json_response(data=report_data, message='Profit report retrieved successfully.')

    context = {
        'profit_data': report_data,
        'period': period,
        'start_date': report_data['start_date'],
        'end_date': report_data['end_date'],
    }
    return render(request, 'reports/profit_report.html', context)


def growth_report_view(request):
    """
    Growth & Trends Report (GET /reports/growth/).
    Week-over-week and month-over-month sales/order volume comparisons.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    authorized, error_response = _check_reports_permission(request)
    if not authorized:
        return error_response

    period, start_date, end_date = _parse_period_and_dates(request)
    try:
        report_data = growth_report(period=period, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        if _wants_json(request):
            return _json_response(message=str(exc), success=False, status=400, errors={'filter': str(exc)})
        return render(request, 'reports/growth.html', {'error': str(exc)}, status=400)

    _log_report_view(
        request,
        report_label='Viewed Growth Report',
        description=f'User {request.user.email} viewed Growth Report for period {period}.',
        metadata={
            'period': period,
            'start_date': str(report_data['start_date']),
            'end_date': str(report_data['end_date']),
            'sales_growth': str(report_data['sales_growth_percentage']),
        },
    )

    if _wants_json(request):
        return _json_response(data=report_data, message='Growth report retrieved successfully.')

    context = {
        'growth_data': report_data,
        'period': period,
        'start_date': report_data['start_date'],
        'end_date': report_data['end_date'],
    }
    return render(request, 'reports/growth.html', context)
