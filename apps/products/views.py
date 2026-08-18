import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Product, ProductCategory, ProductImage, ProductPriceHistory
from .services import (
    MAX_PRODUCT_IMAGE_SIZE,
    _can_manage_product_images,
    _serialize_product_image,
    delete_product_image,
    set_primary_product_image,
    update_product_image,
    upload_product_image,
)

User = get_user_model()


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


# ============================================================================
# AUTHORIZATION HELPERS
# ============================================================================

def _is_authenticated(request):
    """Check if user is authenticated."""
    return request.user and request.user.is_authenticated


def _can_manage_products(user):
    """Check if user can create/update/deactivate products."""
    if not user or not user.is_authenticated:
        return False
    return user.role in ('OWNER', 'MANAGER')


def _can_manage_categories(user):
    """Check if user can create/update/deactivate categories."""
    if not user or not user.is_authenticated:
        return False
    return user.role in ('OWNER', 'MANAGER')


def _can_change_prices(user):
    """Check if user can change product prices."""
    if not user or not user.is_authenticated:
        return False
    return user.role in ('OWNER', 'MANAGER')


# ============================================================================
# PRODUCT IMAGE MANAGEMENT ENDPOINTS
# ============================================================================

@require_http_methods(['POST'])
def product_image_upload(request, product_id):
    """POST /products/<id>/images/"""
    if not _is_authenticated(request):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_manage_product_images(request.user):
        return _json_response(message='You do not have permission to upload product images.', success=False, status=403)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return _json_response(message='Product not found.', success=False, status=404)

    uploaded_file = request.FILES.get('image')
    if not uploaded_file:
        return _json_response(message='Validation failed.', success=False, status=400, errors={'image': 'Image file is required.'})

    try:
        image = upload_product_image(
            product_id=product.id,
            uploaded_file=uploaded_file,
            alt_text=request.POST.get('alt_text', ''),
            display_order=request.POST.get('display_order'),
            is_primary=request.POST.get('is_primary') in ('true', 'True', '1', 'yes', 'on'),
        )
    except ValidationError as exc:
        return _json_response(message='Image upload failed.', success=False, status=400, errors=exc.message_dict if hasattr(exc, 'message_dict') else {'image': str(exc)})
    except Exception as exc:
        return _json_response(message='An error occurred while uploading the image.', success=False, status=500, errors={'detail': str(exc)})

    return _json_response(data=_serialize_product_image(image), message='Image uploaded successfully.', status=201)


@require_http_methods(['PATCH', 'DELETE'])
def product_image_detail(request, product_id, image_id):
    """PATCH/DELETE /products/<id>/images/<image_id>/"""
    if not _is_authenticated(request):
        return _json_response(message='Authentication required.', success=False, status=401)

    if not _can_manage_product_images(request.user):
        return _json_response(message='You do not have permission to manage product images.', success=False, status=403)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return _json_response(message='Product not found.', success=False, status=404)

    try:
        image = ProductImage.objects.get(product=product, id=image_id)
    except ProductImage.DoesNotExist:
        return _json_response(message='Image not found.', success=False, status=404)

    if request.method == 'PATCH':
        if request.content_type and 'application/json' in request.content_type:
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                return _json_response(message='Invalid JSON.', success=False, status=400, errors={'body': 'Request body must be valid JSON.'})
        else:
            payload = request.POST.dict()

        if not payload:
            return _json_response(message='Validation failed.', success=False, status=400, errors={'detail': 'No valid image fields were provided for update.'})

        alt_text = payload.get('alt_text', None)
        display_order = payload.get('display_order', None)
        is_primary_value = payload.get('is_primary', None)

        if 'is_primary' in payload:
            if not isinstance(is_primary_value, bool):
                return _json_response(
                    message='Image update failed.',
                    success=False,
                    status=400,
                    errors={'is_primary': 'is_primary must be a boolean value.'},
                )

        try:
            updated = update_product_image(
                product_id=product.id,
                image_id=image.id,
                alt_text=alt_text,
                display_order=display_order,
                is_primary=is_primary_value,
            )
        except ValidationError as exc:
            return _json_response(message='Image update failed.', success=False, status=400, errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': str(exc)})
        except Exception as exc:
            return _json_response(message='An error occurred while updating the image.', success=False, status=500, errors={'detail': str(exc)})

        return _json_response(data=_serialize_product_image(updated), message='Image updated successfully.')

    try:
        result = delete_product_image(product.id, image.id)
    except Exception as exc:
        return _json_response(message='An error occurred while deleting the image.', success=False, status=500, errors={'detail': str(exc)})

    return _json_response(data=result, message='Image deleted successfully.')


# ============================================================================
# PRODUCT MANAGEMENT ENDPOINTS
# ============================================================================

@require_http_methods(['POST'])
def product_create(request):
    """
    POST /products/create/

    Create a new product.

    Required authentication: OWNER or MANAGER

    Request body:
    {
        "name": "Product Name",
        "sku": "UNIQUE-SKU",
        "category_id": 1,
        "selling_price": "100.00",
        "cost_price": "60.00" (optional),
        "reorder_level": 5 (optional, default: 0),
        "description": "Product description" (optional),
        "is_active": true (optional, default: true)
    }
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_products(request.user):
        return _json_response(
            message='You do not have permission to create products.',
            success=False,
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_response(
            message='Invalid JSON.',
            success=False,
            status=400,
            errors={'body': 'Request body must be valid JSON.'},
        )

    errors = {}

    # Validate required fields
    if not data.get('name'):
        errors['name'] = 'Product name is required.'
    if not data.get('sku'):
        errors['sku'] = 'SKU is required.'
    if 'category_id' not in data:
        errors['category_id'] = 'Category ID is required.'
    if 'selling_price' not in data:
        errors['selling_price'] = 'Selling price is required.'

    if errors:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=errors,
        )

    # Get and validate category
    try:
        category_id = int(data['category_id'])
        category = ProductCategory.objects.get(id=category_id)
    except (ValueError, TypeError):
        return _json_response(
            message='Invalid category ID.',
            success=False,
            status=400,
            errors={'category_id': 'Category ID must be an integer.'},
        )
    except ProductCategory.DoesNotExist:
        return _json_response(
            message='Category not found.',
            success=False,
            status=404,
            errors={'category_id': 'Category does not exist.'},
        )

    # Validate prices
    try:
        selling_price = Decimal(str(data['selling_price']))
        if selling_price < 0:
            raise ValueError('Selling price cannot be negative.')
    except (ValueError, TypeError) as e:
        return _json_response(
            message='Invalid selling price.',
            success=False,
            status=400,
            errors={'selling_price': str(e) or 'Selling price must be a valid decimal.'},
        )

    cost_price = None
    if data.get('cost_price') is not None:
        try:
            cost_price = Decimal(str(data['cost_price']))
            if cost_price < 0:
                raise ValueError('Cost price cannot be negative.')
        except (ValueError, TypeError) as e:
            return _json_response(
                message='Invalid cost price.',
                success=False,
                status=400,
                errors={'cost_price': str(e) or 'Cost price must be a valid decimal.'},
            )

    # Validate reorder level
    reorder_level = data.get('reorder_level', 0)
    try:
        reorder_level = int(reorder_level)
        if reorder_level < 0:
            raise ValueError('Reorder level cannot be negative.')
    except (ValueError, TypeError) as e:
        return _json_response(
            message='Invalid reorder level.',
            success=False,
            status=400,
            errors={'reorder_level': str(e) or 'Reorder level must be a non-negative integer.'},
        )

    # Check for duplicate SKU
    if Product.objects.filter(sku=data['sku'].strip()).exists():
        return _json_response(
            message='SKU already exists.',
            success=False,
            status=409,
            errors={'sku': 'A product with this SKU already exists.'},
        )

    # Create product
    try:
        product = Product.objects.create(
            name=data['name'].strip(),
            sku=data['sku'].strip(),
            category=category,
            selling_price=selling_price,
            cost_price=cost_price,
            reorder_level=reorder_level,
            description=data.get('description', '').strip() or '',
            is_active=data.get('is_active', True),
        )
    except ValidationError as e:
        return _json_response(
            message='Product creation failed.',
            success=False,
            status=400,
            errors=e.error_dict if hasattr(e, 'error_dict') else {'detail': str(e)},
        )
    except Exception as e:
        return _json_response(
            message='An error occurred while creating the product.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    product_data = _serialize_product_detail(product)
    return _json_response(
        data=product_data,
        message='Product created successfully.',
        status=201,
    )


@require_http_methods(['POST'])
def product_update(request, product_id):
    """
    POST /products/<id>/update/

    Update an existing product.

    Required authentication: OWNER or MANAGER

    Request body (all fields optional):
    {
        "name": "New Name",
        "category_id": 2,
        "selling_price": "120.00",
        "cost_price": "70.00",
        "reorder_level": 8,
        "description": "Updated description",
        "is_active": true
    }
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_products(request.user):
        return _json_response(
            message='You do not have permission to update products.',
            success=False,
            status=403,
        )

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return _json_response(
            message='Product not found.',
            success=False,
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_response(
            message='Invalid JSON.',
            success=False,
            status=400,
            errors={'body': 'Request body must be valid JSON.'},
        )

    errors = {}

    # Update name if provided
    if 'name' in data:
        if not data['name']:
            errors['name'] = 'Product name cannot be empty.'
        else:
            product.name = data['name'].strip()

    # Update category if provided
    if 'category_id' in data:
        try:
            category_id = int(data['category_id'])
            category = ProductCategory.objects.get(id=category_id)
            product.category = category
        except (ValueError, TypeError):
            errors['category_id'] = 'Category ID must be an integer.'
        except ProductCategory.DoesNotExist:
            errors['category_id'] = 'Category does not exist.'

    # Update selling price if provided
    if 'selling_price' in data:
        raw_price = data['selling_price']

        if raw_price is None or (isinstance(raw_price, str) and not raw_price.strip()):
            errors['selling_price'] = 'Selling price is required.'
        else:
            try:
                price = Decimal(str(raw_price))
                if not price.is_finite():
                    raise ValueError('Selling price must be a valid decimal.')
                if price < 0:
                    raise ValueError('Selling price cannot be negative.')

                if price != product.selling_price:
                    product.record_price_change(
                        new_price=price,
                        changed_by=request.user,
                        reason=(data.get('price_change_reason') or data.get('reason') or '').strip(),
                    )
                else:
                    product.selling_price = price
            except (InvalidOperation, ValueError, TypeError) as e:
                errors['selling_price'] = str(e) or 'Selling price must be a valid decimal.'

    # Update cost price if provided
    if 'cost_price' in data:
        if data['cost_price'] is None:
            product.cost_price = None
        else:
            try:
                price = Decimal(str(data['cost_price']))
                if price < 0:
                    raise ValueError('Cost price cannot be negative.')
                product.cost_price = price
            except (ValueError, TypeError) as e:
                errors['cost_price'] = str(e) or 'Cost price must be a valid decimal.'

    # Update reorder level if provided
    if 'reorder_level' in data:
        try:
            level = int(data['reorder_level'])
            if level < 0:
                raise ValueError('Reorder level cannot be negative.')
            product.reorder_level = level
        except (ValueError, TypeError) as e:
            errors['reorder_level'] = str(e) or 'Reorder level must be a non-negative integer.'

    # Update description if provided
    if 'description' in data:
        product.description = data['description'].strip() if data['description'] else ''

    # Update is_active if provided
    if 'is_active' in data:
        product.is_active = bool(data['is_active'])

    if errors:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=errors,
        )

    # Save product
    try:
        product.save()
    except ValidationError as e:
        return _json_response(
            message='Product update failed.',
            success=False,
            status=400,
            errors=e.error_dict if hasattr(e, 'error_dict') else {'detail': str(e)},
        )
    except Exception as e:
        return _json_response(
            message='An error occurred while updating the product.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    product_data = _serialize_product_detail(product)
    return _json_response(
        data=product_data,
        message='Product updated successfully.',
    )


@require_http_methods(['POST'])
def product_deactivate(request, product_id):
    """
    POST /products/<id>/deactivate/

    Deactivate a product (mark as inactive without deleting).

    Required authentication: OWNER or MANAGER
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_products(request.user):
        return _json_response(
            message='You do not have permission to deactivate products.',
            success=False,
            status=403,
        )

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return _json_response(
            message='Product not found.',
            success=False,
            status=404,
        )

    if not product.is_active:
        return _json_response(
            message='Product is already deactivated.',
            success=False,
            status=400,
        )

    product.is_active = False
    try:
        product.save()
    except Exception as e:
        return _json_response(
            message='An error occurred while deactivating the product.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    product_data = _serialize_product_detail(product)
    return _json_response(
        data=product_data,
        message='Product deactivated successfully.',
    )


@require_http_methods(['POST'])
def product_change_price(request, product_id):
    """
    POST /products/<id>/change-price/

    Change the selling price of a product and record price history.

    Required authentication: OWNER or MANAGER

    Request body:
    {
        "new_price": "150.00",
        "reason": "Market adjustment" (optional)
    }
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_change_prices(request.user):
        return _json_response(
            message='You do not have permission to change prices.',
            success=False,
            status=403,
        )

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return _json_response(
            message='Product not found.',
            success=False,
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_response(
            message='Invalid JSON.',
            success=False,
            status=400,
            errors={'body': 'Request body must be valid JSON.'},
        )

    if 'new_price' not in data:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'new_price': 'New price is required.'},
        )

    try:
        new_price = Decimal(str(data['new_price']))
        if new_price < 0:
            raise ValueError('Price cannot be negative.')
    except (ValueError, TypeError) as e:
        return _json_response(
            message='Invalid price.',
            success=False,
            status=400,
            errors={'new_price': str(e) or 'Price must be a valid decimal.'},
        )

    reason = data.get('reason', '').strip() or ''

    try:
        history = product.record_price_change(
            new_price=new_price,
            changed_by=request.user,
            reason=reason,
        )
    except ValidationError as e:
        return _json_response(
            message='Price change failed.',
            success=False,
            status=400,
            errors={'detail': str(e)},
        )
    except Exception as e:
        return _json_response(
            message='An error occurred while changing the price.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    # If price didn't actually change, record that
    if history is None:
        return _json_response(
            message='Price did not change.',
            success=False,
            status=400,
            errors={'detail': 'New price is the same as current price.'},
        )

    product_data = _serialize_product_detail(product)
    return _json_response(
        data=product_data,
        message='Product price changed successfully.',
    )


# ============================================================================
# CATEGORY MANAGEMENT ENDPOINTS
# ============================================================================

@require_http_methods(['POST'])
def category_create(request):
    """
    POST /products/categories/create/

    Create a new product category.

    Required authentication: OWNER or MANAGER

    Request body:
    {
        "name": "Category Name",
        "description": "Category description" (optional),
        "is_active": true (optional, default: true)
    }
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_categories(request.user):
        return _json_response(
            message='You do not have permission to create categories.',
            success=False,
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_response(
            message='Invalid JSON.',
            success=False,
            status=400,
            errors={'body': 'Request body must be valid JSON.'},
        )

    errors = {}

    # Validate required fields
    if not data.get('name'):
        errors['name'] = 'Category name is required.'

    if errors:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=errors,
        )

    # Check for duplicate name
    if ProductCategory.objects.filter(name=data['name'].strip()).exists():
        return _json_response(
            message='Category name already exists.',
            success=False,
            status=409,
            errors={'name': 'A category with this name already exists.'},
        )

    # Create category
    try:
        category = ProductCategory.objects.create(
            name=data['name'].strip(),
            description=data.get('description', '').strip() or '',
            is_active=data.get('is_active', True),
        )
    except ValidationError as e:
        return _json_response(
            message='Category creation failed.',
            success=False,
            status=400,
            errors=e.error_dict if hasattr(e, 'error_dict') else {'detail': str(e)},
        )
    except Exception as e:
        return _json_response(
            message='An error occurred while creating the category.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    category_data = _serialize_category(category)
    return _json_response(
        data=category_data,
        message='Category created successfully.',
        status=201,
    )


@require_http_methods(['POST'])
def category_update(request, category_id):
    """
    POST /products/categories/<id>/update/

    Update an existing product category.

    Required authentication: OWNER or MANAGER

    Request body (all fields optional):
    {
        "name": "New Category Name",
        "description": "Updated description",
        "is_active": true
    }
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_categories(request.user):
        return _json_response(
            message='You do not have permission to update categories.',
            success=False,
            status=403,
        )

    try:
        category = ProductCategory.objects.get(id=category_id)
    except ProductCategory.DoesNotExist:
        return _json_response(
            message='Category not found.',
            success=False,
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_response(
            message='Invalid JSON.',
            success=False,
            status=400,
            errors={'body': 'Request body must be valid JSON.'},
        )

    errors = {}

    # Update name if provided
    if 'name' in data:
        if not data['name']:
            errors['name'] = 'Category name cannot be empty.'
        else:
            # Check for duplicate name (excluding current category)
            if ProductCategory.objects.filter(name=data['name'].strip()).exclude(id=category.id).exists():
                errors['name'] = 'A category with this name already exists.'
            else:
                category.name = data['name'].strip()

    # Update description if provided
    if 'description' in data:
        category.description = data['description'].strip() if data['description'] else ''

    # Update is_active if provided
    if 'is_active' in data:
        category.is_active = bool(data['is_active'])

    if errors:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=errors,
        )

    # Save category
    try:
        category.save()
    except ValidationError as e:
        return _json_response(
            message='Category update failed.',
            success=False,
            status=400,
            errors=e.error_dict if hasattr(e, 'error_dict') else {'detail': str(e)},
        )
    except Exception as e:
        return _json_response(
            message='An error occurred while updating the category.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    category_data = _serialize_category(category)
    return _json_response(
        data=category_data,
        message='Category updated successfully.',
    )


@require_http_methods(['POST'])
def category_deactivate(request, category_id):
    """
    POST /products/categories/<id>/deactivate/

    Deactivate a category (mark as inactive).

    Required authentication: OWNER or MANAGER

    Note: Cannot deactivate a category that has active products.
    """
    if not _is_authenticated(request):
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_categories(request.user):
        return _json_response(
            message='You do not have permission to deactivate categories.',
            success=False,
            status=403,
        )

    try:
        category = ProductCategory.objects.get(id=category_id)
    except ProductCategory.DoesNotExist:
        return _json_response(
            message='Category not found.',
            success=False,
            status=404,
        )

    if not category.is_active:
        return _json_response(
            message='Category is already deactivated.',
            success=False,
            status=400,
        )

    # Check if category has active products
    active_products = category.products.filter(is_active=True).count()
    if active_products > 0:
        return _json_response(
            message='Cannot deactivate a category with active products.',
            success=False,
            status=409,
            errors={'detail': f'This category has {active_products} active product(s).'},
        )

    category.is_active = False
    try:
        category.save()
    except Exception as e:
        return _json_response(
            message='An error occurred while deactivating the category.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    category_data = _serialize_category(category)
    return _json_response(
        data=category_data,
        message='Category deactivated successfully.',
    )
