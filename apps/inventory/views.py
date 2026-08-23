from django.db.models import F, Q
from django.http import JsonResponse

from .models import InventoryItem, StockMovement


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
