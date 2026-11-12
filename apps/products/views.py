import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import role_required, _request_wants_json as _wants_json

from .models import Product, ProductCategory, ProductImage, ProductPriceHistory
from .services import (
    MAX_PRODUCT_IMAGE_SIZE,
    _can_manage_product_images,
    _serialize_product_image,
    _validate_uploaded_image,
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


def _is_staff_user(user):
    """Check whether a user has staff/management authorization to view cost and profit margins."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in ('OWNER', 'MANAGER', 'STAFF', 'CASHIER')


def _serialize_product_brief(product, include_inventory=False, user=None):
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

    if _is_staff_user(user):
        data['cost_price'] = str(product.cost_price) if product.cost_price is not None else None
        data['gross_profit'] = str(product.gross_profit)
        data['gross_margin_percentage'] = str(product.gross_margin_percentage)

    # Add primary image if available
    if hasattr(product, '_prefetched_objects_cache') and 'images' in product._prefetched_objects_cache:
        images = list(product.images.all())
        primary = next((img for img in images if img.is_primary), None) or (images[0] if images else None)
    else:
        primary = product.primary_image

    if primary and primary.image:
        img_dict = {
            'id': primary.id,
            'url': primary.image.url,
            'alt_text': primary.alt_text,
        }
        data['image'] = img_dict
        data['image_url'] = primary.image.url
        data['primary_image'] = img_dict
    else:
        data['image'] = None
        data['image_url'] = None
        data['primary_image'] = None

    # Add inventory if available
    if include_inventory:
        inv = getattr(product, 'inventory_item', None)
        if inv is not None:
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


def _serialize_product_detail(product, user=None):
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
        'reorder_level': product.reorder_level,
        'is_active': product.is_active,
        'created_at': product.created_at.isoformat(),
        'updated_at': product.updated_at.isoformat(),
    }

    if _is_staff_user(user):
        data['cost_price'] = str(product.cost_price) if product.cost_price is not None else None
        data['gross_profit'] = str(product.gross_profit)
        data['gross_margin_percentage'] = str(product.gross_margin_percentage)

    # Add all images
    images = list(product.images.all())
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
    primary = next((img for img in images if img.is_primary), None) or (images[0] if images else None)
    if primary and primary.image:
        primary_dict = {
            'id': primary.id,
            'url': primary.image.url,
            'alt_text': primary.alt_text,
        }
        data['primary_image'] = primary_dict
        data['image'] = primary_dict
        data['image_url'] = primary.image.url
    else:
        data['primary_image'] = None
        data['image'] = None
        data['image_url'] = None

    # Add inventory info
    inv = getattr(product, 'inventory_item', None)
    if inv is not None:
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

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/products/")
        if getattr(request.user, 'role', None) == 'CUSTOMER':
            return redirect('/customer/products/')
        return render(request, 'products/products.html', {})

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
        'products': [_serialize_product_brief(p, include_inventory=True, user=request.user) for p in paginated_products],
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
        if not _wants_json(request):
            raise Http404('Product not found.')
        return _json_response(
            message='Product not found.',
            success=False,
            status=404,
        )

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/products/{product_id}/")
        if getattr(request.user, 'role', None) == 'CUSTOMER':
            return redirect(f'/customer/products/{product_id}/')
        return render(request, 'products/product_detail.html', {
            'product_id': product_id,
            'product': product,
            'active_module': 'products',
        })

    data = _serialize_product_detail(product, user=request.user)
    return _json_response(
        data=data,
        message='Product retrieved successfully.',
    )


def product_edit_view(request, product_id):
    """
    GET /products/<id>/edit/
    Product edit interface.
    """
    if not request.user or not getattr(request.user, 'is_authenticated', False):
        return redirect(f"{reverse('accounts:login')}?next=/products/{product_id}/edit/")
    if not _can_manage_products(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have permission to edit products.')
    try:
        product = Product.objects.select_related('category').prefetch_related('images', 'inventory_item').get(id=product_id)
    except Product.DoesNotExist:
        raise Http404('Product not found.')
    categories = list(ProductCategory.objects.all().order_by('name'))
    return render(request, 'products/edit_product.html', {
        'product': product,
        'categories': categories,
        'active_module': 'products',
        'active_tab': 'catalog',
    })


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

    if not _wants_json(request):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return redirect(f"{reverse('accounts:login')}?next=/products/categories/")
        if getattr(request.user, 'role', None) == 'CUSTOMER':
            return redirect('/customer/dashboard/')
        return render(request, 'products/categories.html', {})

    categories = ProductCategory.objects.filter(is_active=True).order_by('name')

    data = {
        'categories': [_serialize_category(cat) for cat in categories],
    }

    return _json_response(
        data=data,
        message='Categories retrieved successfully.',
    )


@role_required('OWNER', 'MANAGER')
def product_price_history_list(request):
    """
    GET /products/price-history/
    Price revision audit history tab.
    Restricted strictly to OWNER and MANAGER roles.
    """
    history_qs = ProductPriceHistory.objects.select_related('product', 'changed_by').order_by('-changed_at')

    search_query = (request.GET.get('search') or '').strip()
    if search_query:
        history_qs = history_qs.filter(
            Q(product__name__icontains=search_query) |
            Q(product__sku__icontains=search_query) |
            Q(reason__icontains=search_query)
        )

    if _wants_json(request):
        data = [
            {
                'id': h.id,
                'product_id': h.product_id,
                'product_name': h.product.name,
                'sku': h.product.sku,
                'previous_price': str(h.previous_price),
                'new_price': str(h.new_price),
                'previous_cost_price': str(h.previous_cost_price) if h.previous_cost_price is not None else None,
                'new_cost_price': str(h.new_cost_price) if h.new_cost_price is not None else None,
                'previous_gross_profit': str(h.previous_gross_profit),
                'new_gross_profit': str(h.new_gross_profit),
                'new_gross_margin_percentage': str(h.new_gross_margin_percentage),
                'reason': h.reason,
                'changed_by': h.changed_by.get_full_name() or h.changed_by.username if h.changed_by else None,
                'changed_at': h.changed_at.isoformat(),
            }
            for h in history_qs[:100]
        ]
        return _json_response(data={'price_history': data}, message='Price history retrieved successfully.')

    total_changes = history_qs.count()
    price_increases = history_qs.filter(new_price__gt=F('previous_price')).count()
    price_reductions = history_qs.filter(new_price__lt=F('previous_price')).count()
    active_products_count = Product.objects.filter(is_active=True).count()

    context = {
        'history_records': history_qs[:100],
        'total_changes': total_changes,
        'price_increases': price_increases,
        'price_reductions': price_reductions,
        'active_products_count': active_products_count,
        'search_query': search_query,
    }
    return render(request, 'products/price_history.html', context)



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

@require_http_methods(['GET', 'POST'])
def product_create(request):
    """
    GET/POST /products/create/

    Create a new product.

    Required authentication: OWNER or MANAGER
    """
    if not _is_authenticated(request):
        if not _wants_json(request):
            return redirect(f"{reverse('accounts:login')}?next=/products/create/")
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if not _can_manage_products(request.user):
        if not _wants_json(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have permission to create products.')
        return _json_response(
            message='You do not have permission to create products.',
            success=False,
            status=403,
        )

    if request.method == 'GET':
        categories = list(ProductCategory.objects.all().order_by('name'))
        return render(request, 'products/add_product.html', {
            'categories': categories,
            'active_module': 'products',
            'active_tab': 'add',
        })

    if request.content_type and 'application/json' in request.content_type:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_response(
                message='Invalid JSON.',
                success=False,
                status=400,
                errors={'body': 'Request body must be valid JSON.'},
            )
    else:
        data = request.POST.dict()

    errors = {}

    # Validate required fields
    if not data.get('name'):
        errors['name'] = 'Product name is required.'
    if not data.get('sku'):
        errors['sku'] = 'SKU is required.'
    if 'category_id' not in data and 'category' not in data:
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
    raw_cat = data.get('category_id') or data.get('category')
    try:
        category_id = int(raw_cat)
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
    selling_price = Decimal('0.00')
    if data.get('selling_price') not in (None, ''):
        try:
            selling_price = Decimal(str(data['selling_price']))
            if not selling_price.is_finite() or selling_price < Decimal('0.00'):
                raise ValueError('Selling price cannot be negative.')
        except (InvalidOperation, ValueError, TypeError) as e:
            return _json_response(
                message='Invalid selling price.',
                success=False,
                status=400,
                errors={'selling_price': str(e) or 'Selling price must be a valid decimal.'},
            )

    cost_price = None
    if data.get('cost_price') not in (None, ''):
        try:
            cost_price = Decimal(str(data['cost_price']))
            if not cost_price.is_finite() or cost_price < Decimal('0.00'):
                raise ValueError('Cost price cannot be negative.')
        except (InvalidOperation, ValueError, TypeError) as e:
            return _json_response(
                message='Invalid cost price.',
                success=False,
                status=400,
                errors={'cost_price': str(e) or 'Cost price must be a valid decimal.'},
            )

    if cost_price is not None and selling_price < cost_price:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'selling_price': 'Selling price cannot be lower than cost price.'},
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

    # Validate uploaded image if provided
    uploaded_image = request.FILES.get('image') or request.FILES.get('product_image')
    if uploaded_image:
        try:
            _validate_uploaded_image(uploaded_image)
        except ValidationError as exc:
            err_dict = exc.message_dict if hasattr(exc, 'message_dict') else {'image': str(exc)}
            return _json_response(
                message='Image validation failed.',
                success=False,
                status=400,
                errors=err_dict,
            )

    # Create product, initial price history, and uploaded image atomically
    try:
        with transaction.atomic():
            product = Product.objects.create(
                name=data['name'].strip(),
                sku=data['sku'].strip(),
                category=category,
                selling_price=selling_price,
                cost_price=cost_price,
                reorder_level=reorder_level,
                allow_pay_on_delivery=bool(data.get('allow_pay_on_delivery', True)),
                description=data.get('description', '').strip() or '',
                is_active=data.get('is_active', True),
            )
            ProductPriceHistory.objects.create(
                product=product,
                previous_price=Decimal('0.00'),
                new_price=product.selling_price,
                previous_cost_price=None,
                new_cost_price=product.cost_price,
                changed_by=request.user,
                reason='Initial catalog pricing',
            )
            if uploaded_image:
                upload_product_image(
                    product_id=product.id,
                    uploaded_file=uploaded_image,
                    alt_text=data.get('alt_text', product.name),
                    is_primary=True,
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

    product.refresh_from_db()
    if not _wants_json(request):
        return redirect(reverse('products:detail', args=[product.id]))

    product_data = _serialize_product_detail(product, user=request.user)
    return _json_response(
        data=product_data,
        message='Product created successfully.',
        status=201,
    )


@require_http_methods(['POST'])
@transaction.atomic
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

    if request.content_type and 'application/json' in request.content_type:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_response(
                message='Invalid JSON.',
                success=False,
                status=400,
                errors={'body': 'Request body must be valid JSON.'},
            )
    else:
        data = request.POST.dict()

    errors = {}

    # Validate uploaded image if provided
    uploaded_image = request.FILES.get('image') or request.FILES.get('product_image')
    if uploaded_image:
        try:
            _validate_uploaded_image(uploaded_image)
        except ValidationError as exc:
            err_dict = exc.message_dict if hasattr(exc, 'message_dict') else {'image': str(exc)}
            return _json_response(
                message='Image validation failed.',
                success=False,
                status=400,
                errors=err_dict,
            )

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

    # Update selling price and cost price if provided
    new_selling = None
    if 'selling_price' in data:
        raw_price = data['selling_price']
        if raw_price is None or (isinstance(raw_price, str) and not raw_price.strip()):
            errors['selling_price'] = 'Selling price is required.'
        else:
            try:
                new_selling = Decimal(str(raw_price))
                if not new_selling.is_finite() or new_selling < Decimal('0.00'):
                    raise ValueError('Selling price cannot be negative.')
            except (InvalidOperation, ValueError, TypeError) as e:
                errors['selling_price'] = str(e) or 'Selling price must be a valid decimal.'

    new_cost = None
    has_cost_update = False
    if 'cost_price' in data:
        has_cost_update = True
        raw_cost = data['cost_price']
        if raw_cost is None or (isinstance(raw_cost, str) and not raw_cost.strip()):
            new_cost = None
        else:
            try:
                new_cost = Decimal(str(raw_cost))
                if not new_cost.is_finite() or new_cost < Decimal('0.00'):
                    raise ValueError('Cost price cannot be negative.')
            except (InvalidOperation, ValueError, TypeError) as e:
                errors['cost_price'] = str(e) or 'Cost price must be a valid decimal.'

    effective_selling = new_selling if new_selling is not None else product.selling_price
    effective_cost = new_cost if has_cost_update else product.cost_price

    if effective_cost is not None and effective_selling < effective_cost:
        if new_selling is not None:
            errors['selling_price'] = 'Selling price cannot be lower than cost price.'
        else:
            errors['cost_price'] = 'Cost price cannot exceed current selling price.'

    price_reason = (data.get('price_change_reason') or data.get('reason') or '').strip()
    selling_changed = (new_selling is not None and new_selling != product.selling_price)
    cost_changed = (has_cost_update and new_cost != product.cost_price)

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

    # Update allow_pay_on_delivery if provided
    if 'allow_pay_on_delivery' in data:
        product.allow_pay_on_delivery = bool(data['allow_pay_on_delivery'])

    if errors:
        transaction.set_rollback(True)
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=errors,
        )

    # Atomically apply price changes and history
    if selling_changed or cost_changed:
        product.record_price_change(
            new_selling_price=effective_selling,
            new_cost_price=effective_cost,
            changed_by=request.user,
            reason=price_reason or 'Catalog product update',
        )

    # Save remaining product fields
    try:
        product.save()
        if uploaded_image:
            upload_product_image(
                product_id=product.id,
                uploaded_file=uploaded_image,
                alt_text=data.get('alt_text', product.name),
                is_primary=True,
            )
    except ValidationError as e:
        transaction.set_rollback(True)
        return _json_response(
            message='Product update failed.',
            success=False,
            status=400,
            errors=e.error_dict if hasattr(e, 'error_dict') else {'detail': str(e)},
        )
    except Exception as e:
        transaction.set_rollback(True)
        return _json_response(
            message='An error occurred while updating the product.',
            success=False,
            status=500,
            errors={'detail': str(e)},
        )

    product.refresh_from_db()
    if not _wants_json(request):
        return redirect(reverse('products:detail', args=[product.id]))

    product_data = _serialize_product_detail(product, user=request.user)
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

    Change the selling price and/or cost price of a product and record price history.

    Required authentication: OWNER or MANAGER

    Request body:
    {
        "new_price": "150.00",
        "new_cost_price": "100.00", (optional)
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

    if 'new_price' not in data and 'selling_price' not in data and 'new_cost_price' not in data and 'cost_price' not in data:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'new_price': 'New price is required.'},
        )

    raw_selling = data.get('new_price') if 'new_price' in data else data.get('selling_price')
    raw_cost = data.get('new_cost_price') if 'new_cost_price' in data else data.get('cost_price')

    target_selling = product.selling_price
    if raw_selling is not None:
        try:
            target_selling = Decimal(str(raw_selling))
            if not target_selling.is_finite() or target_selling < Decimal('0.00'):
                raise ValueError('Price cannot be negative.')
        except (InvalidOperation, ValueError, TypeError) as e:
            return _json_response(
                message='Invalid price.',
                success=False,
                status=400,
                errors={'new_price': str(e) or 'Price must be a valid decimal.'},
            )

    target_cost = product.cost_price
    if raw_cost is not None:
        try:
            target_cost = Decimal(str(raw_cost))
            if not target_cost.is_finite() or target_cost < Decimal('0.00'):
                raise ValueError('Cost price cannot be negative.')
        except (InvalidOperation, ValueError, TypeError) as e:
            return _json_response(
                message='Invalid cost price.',
                success=False,
                status=400,
                errors={'new_cost_price': str(e) or 'Cost price must be a valid decimal.'},
            )

    if target_cost is not None and target_selling < target_cost:
        return _json_response(
            message='Price change failed.',
            success=False,
            status=400,
            errors={'new_price': 'Selling price cannot be lower than cost price.'},
        )

    reason = data.get('reason', '').strip() or ''

    try:
        history = product.record_price_change(
            new_selling_price=target_selling,
            new_cost_price=target_cost,
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

    product_data = _serialize_product_detail(product, user=request.user)
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


# ============================================================================
# CUSTOMER STOREFRONT CATALOG VIEWS
# ============================================================================

def customer_product_list(request):
    """
    GET /customer/products/

    Customer catalog browsing with category filtering, keyword search (?q= or ?search=),
    price sorting, stock availability filtering, and pagination.
    Dual response format: HTML template rendering and JSON API (?format=json).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    search_query = (request.GET.get('q') or request.GET.get('search') or '').strip().lower()
    category_filter = (request.GET.get('category') or '').strip()
    stock_filter = (request.GET.get('stock') or '').strip().upper()
    sort_by = (request.GET.get('sort_by') or request.GET.get('sort') or 'name').strip().lower()

    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
    except (ValueError, TypeError):
        page = 1
        page_size = 10

    products_qs = Product.objects.filter(is_active=True)

    if category_filter and category_filter != 'all':
        try:
            category_id = int(category_filter)
            products_qs = products_qs.filter(
                Q(category__id=category_id) | Q(category__slug=category_filter)
            )
        except ValueError:
            products_qs = products_qs.filter(category__slug=category_filter)

    if search_query:
        products_qs = products_qs.filter(
            Q(name__icontains=search_query)
            | Q(sku__icontains=search_query)
            | Q(category__name__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    if sort_by in ('price_asc', 'price', 'low_to_high'):
        products_qs = products_qs.order_by('selling_price')
    elif sort_by in ('price_desc', '-price', 'high_to_low'):
        products_qs = products_qs.order_by('-selling_price')
    else:
        products_qs = products_qs.order_by('name')

    products_qs = products_qs.select_related('category').prefetch_related(
        'images',
        Prefetch('inventory_item'),
    )

    products_list_all = list(products_qs)
    if stock_filter and stock_filter != 'ALL':
        products_list_all = [
            p for p in products_list_all
            if (hasattr(p, 'inventory_item') and p.inventory_item and p.inventory_item.stock_status == stock_filter)
            or ((not hasattr(p, 'inventory_item') or not p.inventory_item) and stock_filter == 'OUT_OF_STOCK')
        ]

    filtered_count = len(products_list_all)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_products = products_list_all[start:end]

    categories_qs = ProductCategory.objects.filter(is_active=True).order_by('name')
    categories_data = [_serialize_category(c) for c in categories_qs]
    serialized_products = [_serialize_product_brief(p, include_inventory=True) for p in paginated_products]

    pagination = {
        'total_count': filtered_count,
        'page': page,
        'page_size': page_size,
        'total_pages': (filtered_count + page_size - 1) // page_size if page_size else 1,
    }

    wants_json = (
        request.GET.get('format') == 'json'
        or 'application/json' in request.headers.get('Accept', '')
    )

    if wants_json:
        return _json_response(
            data={
                'products': serialized_products,
                'categories': categories_data,
                'pagination': pagination,
            },
            message='Products retrieved successfully.',
        )

    cart_item_count = 0
    if hasattr(request, 'session'):
        from apps.orders.cart import CustomerCart
        cart_item_count = CustomerCart(request).get_cart_data()['item_count']

    context = {
        'products': serialized_products,
        'raw_products': paginated_products,
        'categories': categories_qs,
        'categories_data': categories_data,
        'pagination': pagination,
        'search_query': search_query,
        'selected_category': category_filter,
        'selected_stock': stock_filter,
        'sort_by': sort_by,
        'cart_item_count': cart_item_count,
    }
    return render(request, 'customer/products.html', context)


def customer_product_detail(request, id=None, product_id=None):
    """
    GET /customer/products/<uuid:id>/ (and /customer/products/<int:id>/, /customer/products/<str:id>/)

    Detail view exposing price, current stock, primary image, images, and description.
    Dual response format: HTML template rendering and JSON API (?format=json).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    target_id = id or product_id or request.GET.get('id')
    if not target_id:
        if request.GET.get('format') == 'json' or 'application/json' in request.headers.get('Accept', ''):
            return _json_response(message='Product identifier is required.', success=False, status=400)
        raise Http404('Product identifier is required.')

    product = None
    target_str = str(target_id).strip()

    if target_str.isdigit():
        product = Product.objects.filter(
            id=int(target_str),
            is_active=True,
        ).select_related('category').prefetch_related('images', Prefetch('inventory_item')).first()

    if not product:
        product = Product.objects.filter(
            slug=target_str,
            is_active=True,
        ).select_related('category').prefetch_related('images', Prefetch('inventory_item')).first()

    if not product:
        product = Product.objects.filter(
            sku=target_str,
            is_active=True,
        ).select_related('category').prefetch_related('images', Prefetch('inventory_item')).first()

    wants_json = (
        request.GET.get('format') == 'json'
        or 'application/json' in request.headers.get('Accept', '')
    )

    if not product:
        if wants_json:
            return _json_response(message='Product not found.', success=False, status=404)
        raise Http404('Product not found.')

    detail_data = _serialize_product_detail(product, user=request.user)

    # Query related products for the recommendation carousel
    related_qs = Product.objects.filter(is_active=True).exclude(pk=product.pk)
    if product.category_id:
        category_matches = related_qs.filter(category_id=product.category_id)
        if category_matches.exists():
            related_qs = category_matches
    related_products_list = list(
        related_qs.select_related('category')
        .prefetch_related('images', Prefetch('inventory_item'))[:6]
    )
    serialized_related = [_serialize_product_detail(rp, user=request.user) for rp in related_products_list]
    detail_data['related_products'] = serialized_related

    if wants_json:
        data = {'product': detail_data, 'related_products': serialized_related}
        data.update(detail_data)
        return _json_response(data=data, message='Product retrieved successfully.')

    context = {
        'product': product,
        'product_data': detail_data,
        'product_json': json.dumps(detail_data),
        'related_products': related_products_list,
        'related_products_json': json.dumps(serialized_related),
    }
    return render(request, 'customer/product_detail.html', context)
