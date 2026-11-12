from datetime import datetime, time
from decimal import Decimal
import json

from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.products.models import Product
from .models import InventoryItem, StockMovement
from .services import adjust_inventory_stock


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
    payload = {
        'success': success,
        'message': message,
    }
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    elif not success:
        payload['errors'] = {}
    return JsonResponse(payload, status=status)


def _wants_json(request):
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


def _can_view_inventory_reports(user):
    """
    Check if user is authorized to view internal inventory reports.
    Permitted roles: OWNER, MANAGER, CASHIER, STAFF.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


def _can_adjust_inventory(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return getattr(user, 'role', None) in ('OWNER', 'MANAGER')


def _parse_date(date_str, field_name='date'):
    """
    Parse a YYYY-MM-DD date string.
    Returns (datetime.date, None) on success or (None, error_dict) on failure.
    """
    if not date_str:
        return None, None
    trimmed = date_str.strip()
    if not trimmed:
        return None, None
    try:
        parsed = datetime.strptime(trimmed, '%Y-%m-%d').date()
        return parsed, None
    except (ValueError, TypeError):
        return None, {field_name: f"Invalid date format for '{field_name}'. Expected YYYY-MM-DD."}


def _build_datetime_range(start_date, end_date):
    """
    Convert start and end dates into timezone-aware datetimes.
    """
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), tz) if start_date else None
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max), tz) if end_date else None
    return start_dt, end_dt


def _parse_pagination(request):
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
    except (TypeError, ValueError):
        page = 1
        page_size = 10
    return page, page_size


def _pagination_payload(total_count, page, page_size):
    return {
        'total_count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': (total_count + page_size - 1) // page_size,
    }


def _serialize_product(product):
    return {
        'id': product.id,
        'name': product.name,
        'slug': product.slug,
        'sku': product.sku,
        'category': {
            'id': product.category.id,
            'name': product.category.name,
            'slug': product.category.slug,
        },
        'selling_price': str(product.selling_price),
        'is_active': product.is_active,
    }


def _serialize_inventory_item(inventory_item, include_timestamps=False):
    data = {
        'id': inventory_item.id,
        'product': _serialize_product(inventory_item.product),
        'sku': inventory_item.product.sku,
        'quantity': inventory_item.quantity,
        'reorder_level': inventory_item.reorder_level,
        'stock_status': inventory_item.stock_status,
        'is_low_stock': inventory_item.is_low_stock,
        'is_out_of_stock': inventory_item.is_out_of_stock,
        'is_active': inventory_item.is_active,
    }
    if include_timestamps:
        data['created_at'] = inventory_item.created_at.isoformat()
        data['updated_at'] = inventory_item.updated_at.isoformat()
    return data


def _serialize_user(user):
    if user is None:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'full_name': user.get_full_name(),
        'role': user.role,
    }


def _serialize_movement(movement):
    return {
        'id': movement.id,
        'movement_type': movement.movement_type,
        'quantity': movement.quantity,
        'delta': movement.quantity,
        'previous_quantity': movement.previous_quantity,
        'new_quantity': movement.new_quantity,
        'reason': movement.reason,
        'reference': movement.reference,
        'created_by': _serialize_user(movement.created_by),
        'created_at': movement.created_at.isoformat(),
    }


def _base_inventory_queryset():
    return InventoryItem.objects.filter(
        is_active=True,
        product__is_active=True,
    ).select_related('product', 'product__category')


def _apply_stock_status_filter(queryset, stock_status):
    if stock_status == 'OUT_OF_STOCK':
        return queryset.filter(quantity=0)
    if stock_status == 'LOW_STOCK':
        return queryset.filter(quantity__gt=0, quantity__lte=F('product__reorder_level'))
    if stock_status == 'IN_STOCK':
        return queryset.filter(quantity__gt=F('product__reorder_level'))
    return queryset


def inventory_list(request):
    """
    GET /inventory/

    Return read-only inventory records with search, stock filters, sorting, and pagination.
    """
    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/inventory/")
        if getattr(request.user, 'role', None) == 'CUSTOMER':
            return redirect('/customer/dashboard/')
        if not _can_view_inventory_reports(request.user):
            return render(request, '403.html', {'message': 'You do not have permission to view inventory.'}, status=403)
        return render(request, 'inventory/inventory.html', {
            'active_module': 'inventory',
            'active_tab': 'items',
        })

    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    search_query = (request.GET.get('search') or '').strip()
    stock_status = (request.GET.get('stock_status') or request.GET.get('stock') or '').strip().upper()
    sort_by = (request.GET.get('sort_by') or 'product_name').strip().lower()
    page, page_size = _parse_pagination(request)

    inventory_qs = _base_inventory_queryset()

    if search_query:
        inventory_qs = inventory_qs.filter(
            Q(product__name__icontains=search_query)
            | Q(product__sku__icontains=search_query)
        )

    inventory_qs = _apply_stock_status_filter(inventory_qs, stock_status)

    allowed_sort_fields = {
        'product_name': 'product__name',
        'name': 'product__name',
        'sku': 'product__sku',
        'quantity': 'quantity',
        'quantity_asc': 'quantity',
        'quantity_desc': '-quantity',
        'reorder_level': 'product__reorder_level',
        'reorder_level_desc': '-product__reorder_level',
        'updated_at': '-updated_at',
        'created_at': '-created_at',
    }
    inventory_qs = inventory_qs.order_by(allowed_sort_fields.get(sort_by, 'product__name'), 'id')

    total_count = inventory_qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(inventory_qs[start:end])

    return _json_response(
        data={
            'inventory': [_serialize_inventory_item(item) for item in items],
            'pagination': _pagination_payload(total_count, page, page_size),
        },
        message='Inventory retrieved successfully.',
    )


def inventory_detail(request, inventory_id):
    """
    GET /inventory/<id>/

    Return a single read-only inventory record.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    try:
        inventory_item = _base_inventory_queryset().get(id=inventory_id)
    except InventoryItem.DoesNotExist:
        return _json_response(message='Inventory item not found.', success=False, status=404)

    return _json_response(
        data=_serialize_inventory_item(inventory_item, include_timestamps=True),
        message='Inventory item retrieved successfully.',
    )


def inventory_adjust(request, inventory_id):
    """
    POST /inventory/<id>/adjust/

    Adjust stock through the authoritative inventory service.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)

    if not request.user or not getattr(request.user, 'is_authenticated', False):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_adjust_inventory(request.user):
        return _json_response(message='You do not have permission to adjust inventory.', success=False, status=403)

    try:
        inventory_item = _base_inventory_queryset().get(id=inventory_id)
    except InventoryItem.DoesNotExist:
        return _json_response(message='Inventory item not found.', success=False, status=404)

    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'body': 'Request body must be valid JSON.'})

    if not isinstance(payload, dict):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'body': 'Request body must be a JSON object.'})

    if 'delta' not in payload:
        return _json_response(message='Validation failed.', success=False, status=400, errors={'delta': 'This field is required.'})

    try:
        delta_value = Decimal(str(payload['delta']))
        if not delta_value.is_finite() or delta_value != delta_value.to_integral_value():
            raise ValueError
        delta = int(delta_value)
    except (ValueError, TypeError, ArithmeticError):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'delta': 'Delta must be a numeric whole number.'})

    reason = payload.get('reason', '')
    reference = payload.get('reference', '')
    if reason is None:
        reason = ''
    if reference is None:
        reference = ''
    if not isinstance(reason, str) or not isinstance(reference, str):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'reason': 'Reason and reference must be text.'})

    previous_quantity = inventory_item.quantity
    try:
        adjusted_item = adjust_inventory_stock(
            inventory_item,
            delta,
            reason=reason,
            reference=reference,
            created_by=request.user,
        )
    except ValidationError as error:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=error.message_dict if hasattr(error, 'message_dict') else {'quantity': error.messages},
        )

    movement = StockMovement.objects.filter(
        inventory_item=adjusted_item,
        previous_quantity=previous_quantity,
        new_quantity=adjusted_item.quantity,
        quantity=delta,
    ).order_by('-id').first()

    return _json_response(
        data={
            'inventory': _serialize_inventory_item(adjusted_item, include_timestamps=True),
            'previous_quantity': previous_quantity,
            'new_quantity': adjusted_item.quantity,
            'delta': delta,
            'movement': _serialize_movement(movement) if movement else None,
            'reason': reason,
            'reference': reference,
        },
        message='Inventory stock adjusted successfully.',
    )


def inventory_movements(request, inventory_id):
    """
    GET /inventory/<id>/movements/

    Return paginated read-only movement history for one inventory record.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    try:
        inventory_item = _base_inventory_queryset().get(id=inventory_id)
    except InventoryItem.DoesNotExist:
        return _json_response(message='Inventory item not found.', success=False, status=404)

    page, page_size = _parse_pagination(request)
    movements_qs = StockMovement.objects.filter(
        inventory_item=inventory_item,
    ).select_related('created_by').order_by('-created_at', '-id')

    total_count = movements_qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    movements = list(movements_qs[start:end])

    return _json_response(
        data={
            'inventory': _serialize_inventory_item(inventory_item),
            'movements': [_serialize_movement(movement) for movement in movements],
            'pagination': _pagination_payload(total_count, page, page_size),
        },
        message='Inventory movements retrieved successfully.',
    )


def _serialize_movement_report_item(movement):
    return {
        'id': movement.id,
        'product': {
            'id': movement.product.id,
            'name': movement.product.name,
            'sku': movement.product.sku,
            'category': {
                'id': movement.product.category.id,
                'name': movement.product.category.name,
                'slug': movement.product.category.slug,
            } if movement.product.category else None,
        },
        'movement_type': movement.movement_type,
        'quantity': movement.quantity,
        'delta': movement.quantity,
        'previous_quantity': movement.previous_quantity,
        'new_quantity': movement.new_quantity,
        'reason': movement.reason,
        'reference': movement.reference,
        'created_by': _serialize_user(movement.created_by),
        'created_at': movement.created_at.isoformat(),
    }


def _serialize_low_stock_item(inventory_item):
    shortage = max(0, inventory_item.product.reorder_level - inventory_item.quantity)
    return {
        'id': inventory_item.id,
        'product': _serialize_product(inventory_item.product),
        'sku': inventory_item.product.sku,
        'quantity': inventory_item.quantity,
        'reorder_level': inventory_item.product.reorder_level,
        'shortage_amount': shortage,
        'stock_status': inventory_item.stock_status,
        'is_low_stock': inventory_item.is_low_stock,
        'is_out_of_stock': inventory_item.is_out_of_stock,
        'urgency': 'CRITICAL' if inventory_item.is_out_of_stock else 'WARNING',
    }


def inventory_report_summary(request):
    """
    GET /inventory/reports/summary/

    Return high-level aggregated inventory metrics.
    Requires authentication (OWNER, MANAGER, CASHIER, STAFF).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/inventory/reports/summary/")
        if getattr(request.user, 'role', None) in ('OWNER', 'MANAGER'):
            return inventory_valuation_view(request)
        elif getattr(request.user, 'role', None) in ('CASHIER', 'STAFF'):
            return render(request, '403.html', {'message': 'You do not have permission to view inventory valuations.'}, status=403)
        return redirect('/customer/dashboard/')

    if not request.user or not getattr(request.user, 'is_authenticated', False):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_view_inventory_reports(request.user):
        return _json_response(message='You do not have permission to view inventory reports.', success=False, status=403)

    summary_qs = InventoryItem.objects.filter(is_active=True, product__is_active=True)
    agg = summary_qs.aggregate(
        total_items=Count('id'),
        total_units=Coalesce(Sum('quantity'), 0),
        selling_value=Coalesce(
            Sum(F('quantity') * F('product__selling_price'), output_field=DecimalField(max_digits=14, decimal_places=2)),
            Decimal('0.00'),
        ),
        cost_value=Coalesce(
            Sum(F('quantity') * Coalesce(F('product__cost_price'), Decimal('0.00')), output_field=DecimalField(max_digits=14, decimal_places=2)),
            Decimal('0.00'),
        ),
        out_of_stock_items=Count('id', filter=Q(quantity=0)),
        low_stock_items=Count('id', filter=Q(quantity__gt=0, quantity__lte=F('product__reorder_level'))),
        in_stock_items=Count('id', filter=Q(quantity__gt=F('product__reorder_level'))),
    )

    total_items = agg['total_items']
    total_units = agg['total_units']
    selling_value = agg['selling_value']
    cost_value = agg['cost_value']
    low_stock_items = agg['low_stock_items']
    out_of_stock_items = agg['out_of_stock_items']
    in_stock_items = agg['in_stock_items']
    active_items = total_items
    total_inventory_value = str(cost_value) if cost_value > 0 else str(selling_value)

    return _json_response(
        data={
            'total_items': total_items,
            'total_units': total_units,
            'total_inventory_value': total_inventory_value,
            'inventory_value': str(selling_value),
            'cost_value': str(cost_value),
            'selling_value': str(selling_value),
            'low_stock_items': low_stock_items,
            'out_of_stock_items': out_of_stock_items,
            'in_stock_items': in_stock_items,
            'active_items': active_items,
        },
        message='Inventory summary retrieved successfully.',
    )


def inventory_report_movements(request):
    """
    GET /inventory/reports/movements/

    Return aggregated stock movements with date filtering and pagination.
    Requires authentication (OWNER, MANAGER, CASHIER, STAFF).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/inventory/reports/movements/")
        if not _can_view_inventory_reports(request.user):
            return render(request, '403.html', {'message': 'You do not have permission to view movement reports.'}, status=403)
        return render(request, 'inventory/stock_history.html', {
            'active_module': 'inventory',
            'active_tab': 'movements',
        })

    if not request.user or not getattr(request.user, 'is_authenticated', False):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_view_inventory_reports(request.user):
        return _json_response(message='You do not have permission to view inventory reports.', success=False, status=403)

    date_from_raw = request.GET.get('date_from')
    date_to_raw = request.GET.get('date_to')

    date_from, err_from = _parse_date(date_from_raw, 'date_from')
    if err_from:
        return _json_response(message='Validation failed.', success=False, status=400, errors=err_from)

    date_to, err_to = _parse_date(date_to_raw, 'date_to')
    if err_to:
        return _json_response(message='Validation failed.', success=False, status=400, errors=err_to)

    if date_from and date_to and date_from > date_to:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'date_from': 'date_from cannot be later than date_to.'},
        )

    start_dt, end_dt = _build_datetime_range(date_from, date_to)
    movements_qs = StockMovement.objects.all()

    if start_dt:
        movements_qs = movements_qs.filter(created_at__gte=start_dt)
    if end_dt:
        movements_qs = movements_qs.filter(created_at__lte=end_dt)

    movement_type = (request.GET.get('movement_type') or '').strip().upper()
    if movement_type:
        movements_qs = movements_qs.filter(movement_type=movement_type)

    product_id = request.GET.get('product_id')
    if product_id:
        try:
            movements_qs = movements_qs.filter(product_id=int(product_id))
        except (ValueError, TypeError):
            pass

    totals = movements_qs.aggregate(
        total_movements=Count('id'),
        stock_in_qty=Coalesce(Sum('quantity', filter=Q(quantity__gt=0)), 0),
        stock_out_qty_neg=Coalesce(Sum('quantity', filter=Q(quantity__lt=0)), 0),
        net_movement=Coalesce(Sum('quantity'), 0),
    )

    total_movements = totals['total_movements']
    stock_in_quantity = totals['stock_in_qty']
    stock_out_quantity = abs(totals['stock_out_qty_neg'])
    net_movement = totals['net_movement']

    type_counts_raw = movements_qs.values('movement_type').annotate(count=Count('id'))
    movement_counts = {item['movement_type']: item['count'] for item in type_counts_raw}

    page, page_size = _parse_pagination(request)
    start = (page - 1) * page_size
    end = start + page_size

    paginated_qs = (
        movements_qs.select_related('product', 'product__category', 'created_by')
        .order_by('-created_at', '-id')
    )
    movements_page = list(paginated_qs[start:end])

    return _json_response(
        data={
            'summary': {
                'total_movements': total_movements,
                'stock_in_quantity': stock_in_quantity,
                'stock_out_quantity': stock_out_quantity,
                'net_movement': net_movement,
                'movement_counts': movement_counts,
                'date_from': date_from.isoformat() if date_from else None,
                'date_to': date_to.isoformat() if date_to else None,
            },
            'stock_in_quantity': stock_in_quantity,
            'stock_out_quantity': stock_out_quantity,
            'net_movement': net_movement,
            'movement_counts': movement_counts,
            'movements': [_serialize_movement_report_item(m) for m in movements_page],
            'pagination': _pagination_payload(total_movements, page, page_size),
        },
        message='Movement report retrieved successfully.',
    )


def inventory_report_low_stock(request):
    """
    GET /inventory/reports/low-stock/

    Return low-stock and out-of-stock items with shortage calculations.
    Requires authentication (OWNER, MANAGER, CASHIER, STAFF).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/inventory/reports/low-stock/")
        if not _can_view_inventory_reports(request.user):
            return render(request, '403.html', {'message': 'You do not have permission to view low stock reports.'}, status=403)
        return render(request, 'inventory/low_stock.html', {
            'active_module': 'inventory',
            'active_tab': 'stock_levels',
        })

    if not request.user or not getattr(request.user, 'is_authenticated', False):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_view_inventory_reports(request.user):
        return _json_response(message='You do not have permission to view inventory reports.', success=False, status=403)

    low_stock_qs = InventoryItem.objects.filter(
        is_active=True,
        product__is_active=True,
        quantity__lte=F('product__reorder_level'),
    ).select_related('product', 'product__category')

    search_query = (request.GET.get('search') or '').strip()
    if search_query:
        low_stock_qs = low_stock_qs.filter(
            Q(product__name__icontains=search_query) | Q(product__sku__icontains=search_query)
        )

    category = (request.GET.get('category') or '').strip()
    if category:
        if category.isdigit():
            low_stock_qs = low_stock_qs.filter(product__category_id=int(category))
        else:
            low_stock_qs = low_stock_qs.filter(product__category__slug=category)

    status_filter = (request.GET.get('status') or request.GET.get('stock_status') or '').strip().upper()
    if status_filter in ('OUT_OF_STOCK', 'CRITICAL'):
        low_stock_qs = low_stock_qs.filter(quantity=0)
    elif status_filter in ('LOW_STOCK', 'WARNING'):
        low_stock_qs = low_stock_qs.filter(quantity__gt=0)

    low_stock_qs = low_stock_qs.order_by('quantity', 'id')

    agg = low_stock_qs.aggregate(
        total_low_stock=Count('id'),
        critical_count=Count('id', filter=Q(quantity=0)),
        warning_count=Count('id', filter=Q(quantity__gt=0)),
    )
    total_count = agg['total_low_stock']
    critical_count = agg['critical_count']
    warning_count = agg['warning_count']

    page, page_size = _parse_pagination(request)
    start = (page - 1) * page_size
    end = start + page_size
    items = list(low_stock_qs[start:end])

    serialized_items = [_serialize_low_stock_item(item) for item in items]

    return _json_response(
        data={
            'summary': {
                'total_low_stock': total_count,
                'critical_count': critical_count,
                'warning_count': warning_count,
            },
            'critical_count': critical_count,
            'warning_count': warning_count,
            'total_low_stock': total_count,
            'items': serialized_items,
            'low_stock_products': serialized_items,
            'pagination': _pagination_payload(total_count, page, page_size),
        },
        message='Low-stock report retrieved successfully.',
    )


@role_required('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
def inventory_low_stock_view(request):
    """
    GET /inventory/low-stock/ (name: 'low_stock')
    Low-stock products overview tab.
    """
    if not _wants_json(request):
        return render(request, 'inventory/low_stock.html', {
            'active_module': 'inventory',
            'active_tab': 'stock_levels',
        })
    return inventory_report_low_stock(request)


@role_required('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
def inventory_history_view(request):
    """
    GET /inventory/history/ (name: 'history')
    Stock movements audit trail tab.
    """
    if not _wants_json(request):
        return render(request, 'inventory/stock_history.html', {
            'active_module': 'inventory',
            'active_tab': 'movements',
        })
    return inventory_report_movements(request)


def _serialize_products_for_intake():
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related('inventory_item', 'images').order_by('name')
    products_data = [
        {
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'current_stock': p.current_stock,
            'cost_price': str(p.cost_price if p.cost_price is not None else Decimal('0.00')),
            'selling_price': str(p.selling_price if p.selling_price is not None else Decimal('0.00')),
            'gross_profit': str(p.gross_profit),
            'gross_margin_percentage': str(p.gross_margin_percentage),
            'image_url': p.primary_image.image.url if p.primary_image and p.primary_image.image else None,
        }
        for p in products
    ]
    return products, products_data


@role_required('OWNER', 'MANAGER')
def inventory_add_stock_view(request):
    """
    GET/POST /inventory/adjust/ (name: 'add_stock')
    Stock intake and adjustments tab.
    Restricted strictly to OWNER and MANAGER roles.
    """
    selected_product_id = request.GET.get('product') or request.GET.get('product_id') or ''
    can_manage_prices = request.user.is_superuser or getattr(request.user, 'role', '') in ('OWNER', 'MANAGER')

    # GET requests render the HTML workspace unless format=json is explicitly requested
    if request.method == 'GET' and request.GET.get('format') != 'json':
        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(selected_product_id) if selected_product_id else '',
            'can_manage_prices': can_manage_prices,
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        })

    if request.method == 'GET':
        products, products_data = _serialize_products_for_intake()
        return _json_response(
            data={
                'products': products_data,
                'selected_product_id': str(selected_product_id) if selected_product_id else '',
            },
            message='Products retrieved for stock intake.',
        )

    # Handle POST stock intake and adjustments
    is_json = (
        'application/json' in getattr(request, 'content_type', '')
        or request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.GET.get('format') == 'json'
        or 'application/json' in (request.headers.get('Accept', '') or '')
    )

    try:
        content_type = getattr(request, 'content_type', '') or ''
        payload = json.loads(request.body or '{}') if 'application/json' in content_type else request.POST
    except (TypeError, ValueError, json.JSONDecodeError):
        errors = {'body': 'Invalid JSON request format.'}
        if is_json:
            return JsonResponse({'success': False, 'message': 'Invalid JSON request format.', 'errors': errors}, status=400)
        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(selected_product_id) if selected_product_id else '',
            'can_manage_prices': can_manage_prices,
            'error_message': 'Invalid form submission.',
            'form': {'errors': errors},
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        }, status=400)

    errors = {}
    product_id = payload.get('product_id') or payload.get('product')

    if not product_id:
        errors['product'] = 'Please select a valid product.'

    product = None
    if product_id:
        try:
            product = Product.objects.get(id=int(product_id))
        except (Product.DoesNotExist, ValueError, TypeError):
            errors['product'] = 'Selected product does not exist.'

    # Normalize and validate action / audit reason strictly
    raw_action = (payload.get('action') or payload.get('reason') or payload.get('movement_type') or 'RESTOCK').strip().upper()
    if raw_action == 'STOCK_IN':
        action_type = 'RESTOCK'
    elif raw_action in ('RESTOCK', 'CORRECTION', 'DAMAGE', 'EXPIRY'):
        action_type = raw_action
    else:
        errors['action'] = f"Invalid audit action '{raw_action}'. Allowed actions are Restock, Correction, Damage, and Expiry."
        action_type = None

    delta = 0
    movement_type = StockMovement.MovementType.STOCK_IN
    reason = ''
    reference = ''
    price_updated = False

    inventory_item = None
    if product:
        inventory_item, _ = InventoryItem.objects.get_or_create(
            product=product,
            defaults={'quantity': 0, 'is_active': True}
        )

    # ------------------------------------------------------------------------
    # 1. RESTOCK ACTION
    # ------------------------------------------------------------------------
    if action_type == 'RESTOCK':
        raw_quantity = payload.get('quantity') or payload.get('delta')
        if raw_quantity in (None, ''):
            errors['quantity'] = 'Quantity received is required.'
        else:
            try:
                q_val = Decimal(str(raw_quantity).strip())
                if not q_val.is_finite() or q_val != q_val.to_integral_value() or q_val <= 0:
                    errors['quantity'] = 'Quantity received must be a positive whole number greater than zero.'
                else:
                    delta = int(q_val)
            except (ValueError, TypeError, ArithmeticError):
                errors['quantity'] = 'Quantity must be a valid whole number.'

        supplier = (payload.get('supplier') or '').strip()
        ref = (payload.get('reference') or '').strip()
        notes = (payload.get('notes') or '').strip()
        ref_parts = [p for p in [supplier and f"Supplier: {supplier}", ref and f"Ref: {ref}", notes] if p]
        reference = ' | '.join(ref_parts)
        reason = f"Restock: {supplier}" if supplier else "Restock"
        movement_type = StockMovement.MovementType.STOCK_IN

        # Optional price updates
        update_pricing = bool(
            payload.get('update_pricing') or payload.get('update_prices') or
            (payload.get('new_selling_price') not in (None, '') and payload.get('new_cost_price') not in (None, ''))
        )
        if update_pricing:
            is_authorized = request.user.is_superuser or getattr(request.user, 'role', '') in ('OWNER', 'MANAGER')
            if not is_authorized:
                errors['update_pricing'] = 'You do not have permission to modify product prices.'
            elif product:
                raw_new_cost = payload.get('new_cost_price') or payload.get('unit_cost')
                raw_new_selling = payload.get('new_selling_price')
                price_change_reason = (payload.get('price_change_reason') or f"Restock price update: {reference or supplier}").strip()

            target_cost = product.cost_price
            if raw_new_cost not in (None, ''):
                try:
                    c_val = Decimal(str(raw_new_cost).strip())
                    if not c_val.is_finite() or c_val < Decimal('0.00'):
                        errors['new_cost_price'] = 'New cost price cannot be negative.'
                    else:
                        target_cost = c_val
                except (ValueError, TypeError, ArithmeticError):
                    errors['new_cost_price'] = 'Cost price must be a valid decimal amount.'

            target_selling = product.selling_price
            if raw_new_selling not in (None, ''):
                try:
                    s_val = Decimal(str(raw_new_selling).strip())
                    if not s_val.is_finite() or s_val < Decimal('0.00'):
                        errors['new_selling_price'] = 'New selling price cannot be negative.'
                    else:
                        target_selling = s_val
                except (ValueError, TypeError, ArithmeticError):
                    errors['new_selling_price'] = 'Selling price must be a valid decimal amount.'

            if target_cost is not None and target_selling < target_cost:
                errors['new_selling_price'] = 'Selling price cannot be lower than cost price.'

            # Check if prices actually changed and apply if valid
            if not errors and (target_selling != product.selling_price or target_cost != product.cost_price):
                price_updated = (target_selling, target_cost, price_change_reason)

        elif payload.get('unit_cost') not in (None, '') and product:
            # Legacy simple unit_cost update without full pricing modal
            try:
                c_val = Decimal(str(payload['unit_cost']).strip())
                if c_val < Decimal('0.00'):
                    errors['unit_cost'] = 'Unit cost cannot be negative.'
                elif product.selling_price < c_val:
                    errors['unit_cost'] = f'Unit cost (₦{c_val:.2f}) cannot exceed current selling price (₦{product.selling_price:.2f}).'
                else:
                    price_updated = (product.selling_price, c_val, f"Restock unit cost update: {reference or supplier}")
            except (ValueError, TypeError, ArithmeticError):
                errors['unit_cost'] = 'Unit cost must be a valid decimal amount.'

    # ------------------------------------------------------------------------
    # 2. CORRECTION ACTION (Inventory Audit)
    # ------------------------------------------------------------------------
    elif action_type == 'CORRECTION':
        raw_actual = payload.get('actual_quantity')
        raw_delta = payload.get('delta') or payload.get('adjustment_quantity')
        notes = (payload.get('notes') or payload.get('explanation') or payload.get('reason') or '').strip()

        if not notes:
            errors['notes'] = 'A meaningful correction explanation is required.'

        if raw_actual not in (None, '') and inventory_item:
            try:
                actual_val = Decimal(str(raw_actual).strip())
                if not actual_val.is_finite() or actual_val != actual_val.to_integral_value() or actual_val < 0:
                    errors['actual_quantity'] = 'Verified stock count must be a non-negative whole number.'
                else:
                    actual_int = int(actual_val)
                    delta = actual_int - inventory_item.quantity
                    if delta == 0:
                        errors['actual_quantity'] = 'Counted quantity is identical to current stock. No correction adjustment needed.'
            except (ValueError, TypeError, ArithmeticError):
                errors['actual_quantity'] = 'Verified count must be a valid whole number.'
        elif raw_delta not in (None, ''):
            try:
                delta_val = Decimal(str(raw_delta).strip())
                if not delta_val.is_finite() or delta_val != delta_val.to_integral_value() or delta_val == 0:
                    errors['quantity'] = 'Adjustment quantity must be a non-zero whole number.'
                else:
                    delta = int(delta_val)
                    if inventory_item and (inventory_item.quantity + delta) < 0:
                        errors['quantity'] = f'Cannot adjust stock below zero. Current stock is {inventory_item.quantity}.'
            except (ValueError, TypeError, ArithmeticError):
                errors['quantity'] = 'Adjustment quantity must be a valid whole number.'
        else:
            errors['quantity'] = 'Either verified physical stock or adjustment quantity is required.'

        movement_type = StockMovement.MovementType.CORRECTION
        reason = f"Correction: {notes}"
        reference = (payload.get('reference') or 'Physical Inventory Audit').strip()

    # ------------------------------------------------------------------------
    # 3. DAMAGE ACTION (Damaged / Defective Stock)
    # ------------------------------------------------------------------------
    elif action_type == 'DAMAGE':
        raw_quantity = payload.get('quantity')
        notes = (payload.get('notes') or payload.get('description') or payload.get('reason') or '').strip()

        if not notes:
            errors['notes'] = 'A description of the damage and cause is required.'

        if raw_quantity in (None, ''):
            errors['quantity'] = 'Damaged quantity is required.'
        else:
            try:
                q_val = Decimal(str(raw_quantity).strip())
                if not q_val.is_finite() or q_val != q_val.to_integral_value() or q_val <= 0:
                    errors['quantity'] = 'Damaged quantity must be a positive whole number greater than zero.'
                else:
                    dmg_qty = int(q_val)
                    if inventory_item and dmg_qty > inventory_item.quantity:
                        errors['quantity'] = f'Damaged quantity ({dmg_qty}) cannot exceed current available stock ({inventory_item.quantity}).'
                    else:
                        delta = -dmg_qty
            except (ValueError, TypeError, ArithmeticError):
                errors['quantity'] = 'Quantity must be a valid whole number.'

        movement_type = StockMovement.MovementType.DAMAGE
        reason = f"Damage: {notes}"
        reference = (payload.get('reference') or 'Shelf Defect / Damage Write-off').strip()

    # ------------------------------------------------------------------------
    # 4. EXPIRY ACTION (Expired Stock)
    # ------------------------------------------------------------------------
    elif action_type == 'EXPIRY':
        raw_quantity = payload.get('quantity')
        notes = (payload.get('notes') or payload.get('reason') or '').strip()
        batch_ref = (payload.get('batch_reference') or payload.get('reference') or '').strip()

        if not notes and not batch_ref:
            errors['notes'] = 'Expiry notes or batch reference is required.'

        if raw_quantity in (None, ''):
            errors['quantity'] = 'Expired quantity is required.'
        else:
            try:
                q_val = Decimal(str(raw_quantity).strip())
                if not q_val.is_finite() or q_val != q_val.to_integral_value() or q_val <= 0:
                    errors['quantity'] = 'Expired quantity must be a positive whole number greater than zero.'
                else:
                    exp_qty = int(q_val)
                    if inventory_item and exp_qty > inventory_item.quantity:
                        errors['quantity'] = f'Expired quantity ({exp_qty}) cannot exceed current available stock ({inventory_item.quantity}).'
                    else:
                        delta = -exp_qty
            except (ValueError, TypeError, ArithmeticError):
                errors['quantity'] = 'Quantity must be a valid whole number.'

        movement_type = StockMovement.MovementType.EXPIRY
        reason = f"Expiry: {notes}" if notes else "Expired Product"
        reference = batch_ref or 'Expired Stock Removal'

    if errors:
        error_msg = next(iter(errors.values())) if errors else 'Invalid stock submission.'
        if is_json:
            return JsonResponse({'success': False, 'message': error_msg, 'errors': errors}, status=400)
        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(product_id) if product_id else '',
            'can_manage_prices': can_manage_prices,
            'error_message': error_msg,
            'form': {'errors': errors},
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        }, status=400)

    try:
        from django.db import transaction
        with transaction.atomic():
            # If price update is requested on Restock, record price change atomically
            if price_updated and product:
                new_selling, new_cost, p_reason = price_updated
                product.record_price_change(
                    new_selling_price=new_selling,
                    new_cost_price=new_cost,
                    changed_by=request.user,
                    reason=p_reason,
                )

            adjusted_item = adjust_inventory_stock(
                inventory_item,
                delta,
                reason=reason,
                reference=reference,
                created_by=request.user,
                movement_type=movement_type,
            )

        if action_type == 'RESTOCK':
            msg = f"Successfully received {delta} units of {product.name}. New stock level: {adjusted_item.quantity} units."
        elif action_type == 'CORRECTION':
            msg = f"Successfully corrected stock for {product.name} by {delta:+d} units. New stock level: {adjusted_item.quantity} units."
        elif action_type == 'DAMAGE':
            msg = f"Successfully deducted {abs(delta)} damaged units of {product.name}. Remaining stock: {adjusted_item.quantity} units."
        else: # EXPIRY
            msg = f"Successfully removed {abs(delta)} expired units of {product.name}. Remaining stock: {adjusted_item.quantity} units."

        if is_json:
            return JsonResponse({
                'success': True,
                'message': msg,
                'data': {
                    'inventory': _serialize_inventory_item(adjusted_item),
                    'product_id': product.id,
                    'product_name': product.name,
                    'delta': delta,
                    'new_quantity': adjusted_item.quantity,
                    'new_stock_level': adjusted_item.quantity,
                    'action': action_type,
                },
            }, status=200)

        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(product.id),
            'can_manage_prices': can_manage_prices,
            'success_message': msg,
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        })
    except ValidationError as e:
        field_errors = e.message_dict if hasattr(e, 'message_dict') else {'quantity': e.messages}
        err_msg = 'Validation failed.'
        if hasattr(e, 'message'):
            err_msg = e.message
        elif field_errors:
            first_val = next(iter(field_errors.values()))
            err_msg = first_val[0] if isinstance(first_val, list) and first_val else str(first_val)
        if is_json:
            return JsonResponse({'success': False, 'message': err_msg, 'errors': field_errors}, status=400)
        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(product_id) if product_id else '',
            'can_manage_prices': can_manage_prices,
            'error_message': err_msg,
            'form': {'errors': field_errors},
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        }, status=400)
    except Exception as e:
        err_msg = str(e)
        if is_json:
            return JsonResponse({'success': False, 'message': err_msg, 'errors': {'detail': err_msg}}, status=400)
        products, products_data = _serialize_products_for_intake()
        return render(request, 'inventory/add_stock.html', {
            'products': products,
            'products_json': json.dumps(products_data),
            'selected_product_id': str(product_id) if product_id else '',
            'can_manage_prices': can_manage_prices,
            'error_message': err_msg,
            'form': {'errors': {'detail': err_msg}},
            'active_module': 'inventory',
            'active_tab': 'adjustments',
        }, status=400)


@role_required('OWNER', 'MANAGER')
def inventory_valuation_view(request):
    """
    GET /inventory/valuation/ (name: 'valuation')
    Cost Valuations & Financial Reports tab.
    Restricted strictly to OWNER and MANAGER roles.
    """
    summary_qs = InventoryItem.objects.filter(is_active=True, product__is_active=True).select_related('product', 'product__category')
    agg = summary_qs.aggregate(
        total_items=Count('id'),
        total_units=Coalesce(Sum('quantity'), 0),
        selling_value=Coalesce(
            Sum(F('quantity') * F('product__selling_price'), output_field=DecimalField(max_digits=14, decimal_places=2)),
            Decimal('0.00'),
        ),
        cost_value=Coalesce(
            Sum(F('quantity') * Coalesce(F('product__cost_price'), Decimal('0.00')), output_field=DecimalField(max_digits=14, decimal_places=2)),
            Decimal('0.00'),
        ),
    )
    total_items = agg['total_items'] or 0
    total_units = agg['total_units'] or 0
    selling_value = agg['selling_value'] or Decimal('0.00')
    cost_value = agg['cost_value'] or Decimal('0.00')
    potential_margin = selling_value - cost_value
    margin_percent = round((potential_margin / selling_value * Decimal('100.0')), 1) if selling_value > 0 else Decimal('0.0')

    if _wants_json(request):
        return _json_response(
            data={
                'total_items': total_items,
                'total_units': total_units,
                'selling_value': str(selling_value),
                'cost_value': str(cost_value),
                'potential_margin': str(potential_margin),
                'margin_percent': float(margin_percent),
            },
            message='Inventory valuation retrieved successfully.',
        )

    # Decorate items for template
    items_list = list(summary_qs.order_by('product__name')[:100])
    for item in items_list:
        cost = getattr(item.product, 'cost_price', None) or Decimal('0.00')
        item.total_cost = (item.quantity * cost)
        item.total_retail = (item.quantity * item.product.selling_price)
        item.potential_profit = item.total_retail - item.total_cost

    context = {
        'active_module': 'inventory',
        'active_tab': 'valuation',
        'total_items': total_items,
        'total_units': total_units,
        'selling_value': f"{selling_value:,.2f}",
        'cost_value': f"{cost_value:,.2f}",
        'potential_margin': f"{potential_margin:,.2f}",
        'margin_percent': margin_percent,
        'items': items_list,
    }
    return render(request, 'inventory/valuation.html', context)
