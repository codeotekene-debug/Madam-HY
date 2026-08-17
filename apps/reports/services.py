from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import models
from django.db.models import Avg, Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.credits.models import CreditAccount, CreditTransaction
from apps.expenses.models import Expense
from apps.inventory.models import InventoryItem
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem


def get_date_range(period='this_month', start_date=None, end_date=None):
    """Return a date range with timezone-aware start/end datetimes for reporting."""
    today = timezone.localdate()
    if start_date and end_date:
        start = start_date
        end = end_date
        return {'start_date': start, 'end_date': end}

    if period == 'today':
        return {'start_date': today, 'end_date': today}
    if period == 'this_week':
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return {'start_date': start, 'end_date': end}
    if period == 'this_month':
        start = today.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
        return {'start_date': start, 'end_date': end}
    if period == 'this_year':
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        return {'start_date': start, 'end_date': end}
    raise ValueError('Unsupported period. Use today, this_week, this_month, this_year, or custom dates.')


def _as_datetime_range(start_date, end_date):
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max), tz)
    return start_dt, end_dt


def sales_report(period='this_month', start_date=None, end_date=None):
    date_range = get_date_range(period=period, start_date=start_date, end_date=end_date)
    start_dt, end_dt = _as_datetime_range(date_range['start_date'], date_range['end_date'])
    queryset = Sale.objects.filter(
        status=Sale.SaleStatus.COMPLETED,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).select_related('cashier', 'customer')

    sales_by_day = list(
        queryset.annotate(day=TruncDate('created_at')).values('day').annotate(
            total_sales=Sum('total'),
            sales_count=Count('id'),
        ).order_by('day')
    )

    by_payment_method = list(
        queryset.values('payment_method').annotate(
            total_sales=Sum('total'),
            sales_count=Count('id'),
        ).order_by('-total_sales')
    )

    by_cashier = list(
        queryset.values('cashier__first_name', 'cashier__last_name').annotate(
            total_sales=Sum('total'),
            sales_count=Count('id'),
        ).order_by('-total_sales')
    )

    product_totals = list(
        SaleItem.objects.filter(sale__in=queryset).values('product__name').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(models.F('quantity') * models.F('unit_price')),
        ).order_by('-total_quantity')[:10]
    )

    sales_by_category = list(
        SaleItem.objects.filter(sale__in=queryset).values('product__category__name').annotate(
            total_sales=Sum(models.F('quantity') * models.F('unit_price')),
        ).order_by('-total_sales')
    )

    total_sales = queryset.aggregate(total_sales=Sum('total'))['total_sales'] or Decimal('0.00')
    sales_count = queryset.count()
    average_sale = queryset.aggregate(avg_sale=Avg('total'))['avg_sale'] or Decimal('0.00')

    return {
        'start_date': date_range['start_date'],
        'end_date': date_range['end_date'],
        'total_sales': total_sales,
        'sales_count': sales_count,
        'average_sale': average_sale,
        'sales_by_day': [
            {
                'day': item['day'],
                'total_sales': item['total_sales'] or Decimal('0.00'),
                'sales_count': item['sales_count'],
            }
            for item in sales_by_day
        ],
        'sales_by_payment_method': [
            {
                'payment_method': item['payment_method'],
                'total_sales': item['total_sales'] or Decimal('0.00'),
                'sales_count': item['sales_count'],
            }
            for item in by_payment_method
        ],
        'sales_by_cashier': [
            {
                'cashier_name': f"{item['cashier__first_name']} {item['cashier__last_name']}".strip() or 'Unknown',
                'total_sales': item['total_sales'] or Decimal('0.00'),
                'sales_count': item['sales_count'],
            }
            for item in by_cashier
        ],
        'top_selling_products': [
            {
                'product_name': item['product__name'],
                'total_quantity': item['total_quantity'],
                'total_revenue': item['total_revenue'] or Decimal('0.00'),
            }
            for item in product_totals
        ],
        'sales_by_category': [
            {
                'category': item['product__category__name'],
                'total_sales': item['total_sales'] or Decimal('0.00'),
            }
            for item in sales_by_category
        ],
    }


def expense_report(period='this_month', start_date=None, end_date=None):
    date_range = get_date_range(period=period, start_date=start_date, end_date=end_date)
    start_dt, end_dt = _as_datetime_range(date_range['start_date'], date_range['end_date'])
    queryset = Expense.objects.filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    )

    total_expenses = queryset.aggregate(total_expenses=Sum('amount'))['total_expenses'] or Decimal('0.00')
    expense_count = queryset.count()

    expenses_by_category = list(
        queryset.values('category').annotate(total_expenses=Sum('amount'), expense_count=Count('id')).order_by('-total_expenses')
    )
    expenses_by_payment_method = list(
        queryset.values('payment_method').annotate(total_expenses=Sum('amount'), expense_count=Count('id')).order_by('-total_expenses')
    )
    by_day = list(
        queryset.annotate(day=TruncDate('expense_date')).values('day').annotate(total_expenses=Sum('amount'), expense_count=Count('id')).order_by('day')
    )
    largest_expenses = list(
        queryset.order_by('-amount')[:10].values('expense_reference', 'vendor', 'amount', 'category', 'expense_date')
    )

    return {
        'start_date': date_range['start_date'],
        'end_date': date_range['end_date'],
        'total_expenses': total_expenses,
        'expense_count': expense_count,
        'expenses_by_category': [
            {
                'category': item['category'],
                'total_expenses': item['total_expenses'] or Decimal('0.00'),
                'expense_count': item['expense_count'],
            }
            for item in expenses_by_category
        ],
        'expenses_by_payment_method': [
            {
                'payment_method': item['payment_method'],
                'total_expenses': item['total_expenses'] or Decimal('0.00'),
                'expense_count': item['expense_count'],
            }
            for item in expenses_by_payment_method
        ],
        'expenses_by_day': [
            {
                'day': item['day'],
                'total_expenses': item['total_expenses'] or Decimal('0.00'),
                'expense_count': item['expense_count'],
            }
            for item in by_day
        ],
        'largest_expenses': [
            {
                'expense_reference': item['expense_reference'],
                'vendor': item['vendor'],
                'amount': item['amount'],
                'category': item['category'],
                'expense_date': item['expense_date'],
            }
            for item in largest_expenses
        ],
    }


def profit_report(period='this_month', start_date=None, end_date=None):
    sales = sales_report(period=period, start_date=start_date, end_date=end_date)
    expenses = expense_report(period=period, start_date=start_date, end_date=end_date)

    revenue = sales['total_sales']
    expenses_total = expenses['total_expenses']

    cost_of_goods_sold = Decimal('0.00')
    range_data = get_date_range(period=period, start_date=start_date, end_date=end_date)
    start_dt, end_dt = _as_datetime_range(range_data['start_date'], range_data['end_date'])
    sale_items = SaleItem.objects.filter(
        sale__status=Sale.SaleStatus.COMPLETED,
        sale__created_at__gte=start_dt,
        sale__created_at__lte=end_dt,
    ).select_related('product')

    for item in sale_items:
        if item.product.cost_price is not None:
            cost_of_goods_sold += (item.quantity * item.product.cost_price)

    gross_profit = revenue - cost_of_goods_sold
    net_profit = gross_profit - expenses_total
    profit_margin = Decimal('0.00')
    if revenue > 0:
        profit_margin = (net_profit / revenue) * Decimal('100')

    return {
        'revenue': revenue,
        'cost_of_goods_sold': cost_of_goods_sold,
        'gross_profit': gross_profit,
        'expenses': expenses_total,
        'net_profit': net_profit,
        'profit_margin': profit_margin.quantize(Decimal('0.01')),
    }


def growth_report(period='this_month', start_date=None, end_date=None):
    current_range = get_date_range(period=period, start_date=start_date, end_date=end_date)
    if period in {'today', 'this_week', 'this_month', 'this_year'}:
        if period == 'today':
            previous_start = current_range['start_date'] - timedelta(days=1)
            previous_end = current_range['end_date'] - timedelta(days=1)
        elif period == 'this_week':
            current_start = current_range['start_date']
            current_end = current_range['end_date']
            previous_start = current_start - timedelta(days=7)
            previous_end = current_end - timedelta(days=7)
        elif period == 'this_month':
            current_start = current_range['start_date']
            current_end = current_range['end_date']
            if current_start.month == 1:
                previous_start = current_start.replace(year=current_start.year - 1, month=12, day=1)
                previous_end = previous_start.replace(day=28) + timedelta(days=4)
                previous_end = previous_end.replace(day=1) - timedelta(days=1)
            else:
                previous_start = current_start.replace(month=current_start.month - 1, day=1)
                previous_end = (previous_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        else:
            previous_start = current_range['start_date'].replace(year=current_range['start_date'].year - 1)
            previous_end = current_range['end_date'].replace(year=current_range['end_date'].year - 1)
    else:
        span = (current_range['end_date'] - current_range['start_date']).days
        previous_start = current_range['start_date'] - timedelta(days=span + 1)
        previous_end = current_range['end_date'] - timedelta(days=span + 1)

    current_sales = sales_report(period=period, start_date=current_range['start_date'], end_date=current_range['end_date'])
    previous_sales = sales_report(period='custom', start_date=previous_start, end_date=previous_end)
    current_expenses = expense_report(period=period, start_date=current_range['start_date'], end_date=current_range['end_date'])
    previous_expenses = expense_report(period='custom', start_date=previous_start, end_date=previous_end)
    current_profit = profit_report(period=period, start_date=current_range['start_date'], end_date=current_range['end_date'])
    previous_profit = profit_report(period='custom', start_date=previous_start, end_date=previous_end)

    sales_growth = Decimal('0.00')
    if previous_sales['total_sales'] > 0:
        sales_growth = ((current_sales['total_sales'] - previous_sales['total_sales']) / previous_sales['total_sales']) * Decimal('100')
    elif current_sales['total_sales'] > 0:
        sales_growth = Decimal('100.00')

    expense_growth = Decimal('0.00')
    if previous_expenses['total_expenses'] > 0:
        expense_growth = ((current_expenses['total_expenses'] - previous_expenses['total_expenses']) / previous_expenses['total_expenses']) * Decimal('100')
    elif current_expenses['total_expenses'] > 0:
        expense_growth = Decimal('100.00')

    profit_growth = Decimal('0.00')
    if previous_profit['net_profit'] > 0:
        profit_growth = ((current_profit['net_profit'] - previous_profit['net_profit']) / previous_profit['net_profit']) * Decimal('100')
    elif current_profit['net_profit'] > 0:
        profit_growth = Decimal('100.00')

    return {
        'current_period_sales': current_sales['total_sales'],
        'previous_period_sales': previous_sales['total_sales'],
        'sales_growth_percentage': sales_growth.quantize(Decimal('0.01')),
        'current_period_expenses': current_expenses['total_expenses'],
        'previous_period_expenses': previous_expenses['total_expenses'],
        'expense_growth_percentage': expense_growth.quantize(Decimal('0.01')),
        'current_period_profit': current_profit['net_profit'],
        'previous_period_profit': previous_profit['net_profit'],
        'profit_growth_percentage': profit_growth.quantize(Decimal('0.01')),
    }


def inventory_summary():
    total_products = Product.objects.count()
    in_stock = InventoryItem.objects.filter(quantity__gt=0).count()
    low_stock = InventoryItem.objects.filter(quantity__lte=F('product__reorder_level')).count()
    out_of_stock = InventoryItem.objects.filter(quantity=0).count()
    total_inventory_quantity = InventoryItem.objects.aggregate(total_quantity=Sum('quantity'))['total_quantity'] or 0
    inventory_value = InventoryItem.objects.select_related('product').aggregate(
        value=Sum(models.F('quantity') * models.F('product__selling_price'))
    )['value'] or Decimal('0.00')

    return {
        'total_products': total_products,
        'products_in_stock': in_stock,
        'low_stock_products': low_stock,
        'out_of_stock_products': out_of_stock,
        'total_inventory_quantity': total_inventory_quantity,
        'inventory_value': inventory_value,
    }


def credit_summary(period='this_month', start_date=None, end_date=None):
    date_range = get_date_range(period=period, start_date=start_date, end_date=end_date)
    total_credit_limit = CreditAccount.objects.aggregate(total_credit_limit=Sum('credit_limit'))['total_credit_limit'] or Decimal('0.00')
    total_outstanding_credit = CreditAccount.objects.aggregate(total_outstanding=Sum('outstanding_balance'))['total_outstanding'] or Decimal('0.00')
    available_credit = total_credit_limit - total_outstanding_credit
    active_credit_accounts = CreditAccount.objects.filter(status=CreditAccount.Status.ACTIVE).count()
    overdue_credit_accounts = CreditAccount.objects.filter(status=CreditAccount.Status.OVERDUE).count()
    start_dt, end_dt = _as_datetime_range(date_range['start_date'], date_range['end_date'])
    repayments_during_period = CreditTransaction.objects.filter(
        transaction_type=CreditTransaction.TransactionType.REPAYMENT,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).aggregate(total_repayed=Sum('amount'))['total_repayed'] or Decimal('0.00')

    return {
        'total_credit_limit': total_credit_limit,
        'total_outstanding_credit': total_outstanding_credit,
        'available_credit': available_credit,
        'active_credit_accounts': active_credit_accounts,
        'overdue_credit_accounts': overdue_credit_accounts,
        'repayments_during_period': repayments_during_period,
    }
