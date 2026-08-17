from decimal import Decimal

from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Product, ProductCategory, ProductImage


def _json_response(data=None, message="Success", success=True, status=200, errors=None):
    """Return a standardized JSON response."""
    payload = {
        'success': success,
        'message': message,
    }
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    return JsonResponse(payload, status=status)


def _serialize_product_brief(product, include_inventory=False):
    """Serialize a product for list responses."""
    data = {
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
        'description': product.description[:200] if product.description else '',
        'is_active': product.is_active,
    }

    # Add primary image if available
    if hasattr(product, '_prefetched_objects_cache') and 'images' in product._prefetched_objects_cache:
        images = product.images.all()
        primary = next((img for img in images if img.is_primary), None)
        if primary:
            data['image'] = {
                'id': primary.id,
                'url': primary.image.url if primary.image else None,
                'alt_text': primary.alt_text,
            }
        elif images:
            img = images[0]
            data['image'] = {
                'id': img.id,
                'url': img.image.url if img.image else None,
                'alt_text': img.alt_text,
            }
    else:
        data['image'] = None

    # Add inventory if available
    if include_inventory and hasattr(product, 'inventory_item'):
        inv = product.inventory_item
        data['stock'] = {
            'quantity': inv.quantity,
            'status': inv.stock_status,
            'is_low_stock': inv.is_low_stock,
            'is_out_of_stock': inv.is_out_of_stock,
        }
    elif include_inventory:
        data['stock'] = {
            'quantity': 0,
            'status': 'OUT_OF_STOCK',
            'is_low_stock': False,
            'is_out_of_stock': True,
        }

    return data


def _serialize_product_detail(product):
    """Serialize a product for detail responses."""
    data = {
        'id': product.id,
        'name': product.name,
        'slug': product.slug,
        'sku': product.sku,
        'description': product.description,
        'category': {
            'id': product.category.id,
            'name': product.category.name,
            'slug': product.category.slug,
        },
        'selling_price': str(product.selling_price),
        'cost_price': str(product.cost_price) if product.cost_price else None,
        'reorder_level': product.reorder_level,
        'is_active': product.is_active,
        'created_at': product.created_at.isoformat(),
        'updated_at': product.updated_at.isoformat(),
    }

    # Add all images
    images = product.images.all()
    data['images'] = [
        {
            'id': img.id,
            'url': img.image.url if img.image else None,
            'alt_text': img.alt_text,
            'display_order': img.display_order,
            'is_primary': img.is_primary,
        }
        for img in images
    ]

    # Add primary image reference
    primary = next((img for img in images if img.is_primary), None)
    data['primary_image'] = {
        'id': primary.id,
        'url': primary.image.url if primary.image else None,
        'alt_text': primary.alt_text,
    } if primary else None

    # Add inventory info
    if hasattr(product, 'inventory_item'):
        inv = product.inventory_item
        data['stock'] = {
            'quantity': inv.quantity,
            'status': inv.stock_status,
            'is_low_stock': inv.is_low_stock,
            'is_out_of_stock': inv.is_out_of_stock,
        }
    else:
        data['stock'] = {
            'quantity': 0,
            'status': 'OUT_OF_STOCK',
            'is_low_stock': False,
            'is_out_of_stock': True,
        }

    return data


def _serialize_category(category):
    """Serialize a category for responses."""
    return {
        'id': category.id,
        'name': category.name,
        'slug': category.slug,
        'description': category.description,
        'is_active': category.is_active,
    }


def products_list(request):
    """
    GET /products/

    Return a list of products with optional filtering and search.

    Query parameters:
    - search: Search by name, SKU, or category
    - category: Filter by category ID or slug
    - stock: Filter by stock status (IN_STOCK, LOW_STOCK, OUT_OF_STOCK)
    - sort_by: Sort by name, price_asc, price_desc (default: name)
    - page: Page number (default: 1)
    - page_size: Results per page (default: 10, max: 100)
    """
    if request.method != 'GET':
        return _json_response(
            message='Only GET is allowed.',
            success=False,
            status=405,
        )

    # Get query parameters
    search_query = (request.GET.get('search') or '').strip().lower()
    category_filter = (request.GET.get('category') or '').strip()
    stock_filter = (request.GET.get('stock') or '').strip().upper()
    sort_by = (request.GET.get('sort_by') or 'name').strip().lower()

    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
    except (ValueError, TypeError):
        page = 1
        page_size = 10

    # Start with active products
    products_qs = Product.objects.filter(is_active=True)

    # Apply category filter
    if category_filter:
        # Try as ID first if it looks numeric, fallback to slug
        try:
            category_id = int(category_filter)
            products_qs = products_qs.filter(
                Q(category__id=category_id) | Q(category__slug=category_filter)
            )
        except ValueError:
            # Not a number, filter by slug only
            products_qs = products_qs.filter(category__slug=category_filter)

    # Apply search
    if search_query:
        products_qs = products_qs.filter(
            Q(name__icontains=search_query)
            | Q(sku__icontains=search_query)
            | Q(category__name__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    # Apply sorting
    if sort_by == 'price_asc':
        products_qs = products_qs.order_by('selling_price')
    elif sort_by == 'price_desc':
        products_qs = products_qs.order_by('-selling_price')
    else:
        products_qs = products_qs.order_by('name')

    # Optimize queries with prefetch
    products_qs = products_qs.select_related('category').prefetch_related(
        'images',
        Prefetch('inventory_item'),
    )

    # Apply stock filter (post-query since it depends on prefetched inventory)
    total_count = products_qs.count()
    products_list_all = list(products_qs)

    if stock_filter:
        products_list_all = [
            p for p in products_list_all
            if (hasattr(p, 'inventory_item') and p.inventory_item.stock_status == stock_filter)
            or (not hasattr(p, 'inventory_item') and stock_filter == 'OUT_OF_STOCK')
        ]

    # Apply pagination
    filtered_count = len(products_list_all)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_products = products_list_all[start:end]

    # Serialize products
    data = {
        'products': [_serialize_product_brief(p, include_inventory=True) for p in paginated_products],
        'pagination': {
            'total_count': filtered_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (filtered_count + page_size - 1) // page_size,
        },
    }

    return _json_response(
        data=data,
        message='Products retrieved successfully.',
    )


def product_detail(request, product_id):
    """
    GET /products/<id>/

    Return detailed information for a single product.
    """
    if request.method != 'GET':
        return _json_response(
            message='Only GET is allowed.',
            success=False,
            status=405,
        )

    try:
        product = Product.objects.select_related('category').prefetch_related(
            'images',
            Prefetch('inventory_item'),
        ).get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return _json_response(
            message='Product not found.',
            success=False,
            status=404,
        )

    data = _serialize_product_detail(product)
    return _json_response(
        data=data,
        message='Product retrieved successfully.',
    )


def categories_list(request):
    """
    GET /products/categories/

    Return a list of active product categories.
    """
    if request.method != 'GET':
        return _json_response(
            message='Only GET is allowed.',
            success=False,
            status=405,
        )

    categories = ProductCategory.objects.filter(is_active=True).order_by('name')

    data = {
        'categories': [_serialize_category(cat) for cat in categories],
    }

    return _json_response(
        data=data,
        message='Categories retrieved successfully.',
    )
