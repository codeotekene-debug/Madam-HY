from datetime import datetime, time
from decimal import Decimal
import json

from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.utils import timezone

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
    return JsonResponse(payload, status=status)


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
