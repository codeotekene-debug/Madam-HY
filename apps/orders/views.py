import json
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone

from apps.products.models import Product

from .models import Order, OrderItem


MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
	payload = {'success': success, 'message': message}
	if data is not None:
		payload['data'] = data
	if errors is not None:
		payload['errors'] = errors
	return JsonResponse(payload, status=status)


def _is_authenticated(user):
	return bool(user and getattr(user, 'is_authenticated', False))


def _can_view_orders(user):
	return _is_authenticated(user) and getattr(user, 'role', None) in (
		*MANAGEMENT_ROLES,
		'CUSTOMER',
	)


def _parse_json_body(request):
	try:
		payload = json.loads(request.body or '{}')
	except (TypeError, ValueError, json.JSONDecodeError):
		return None, {'body': 'Request body must be valid JSON.'}
	if not isinstance(payload, dict):
		return None, {'body': 'Request body must be a JSON object.'}
	return payload, None


def _parse_positive_integer(value):
	if isinstance(value, bool):
		raise ValueError
	quantity = int(value)
	if str(value).strip() != str(quantity) or quantity <= 0:
		raise ValueError
	return quantity


def _parse_date(value, field_name):
	if not value:
		return None, None
	try:
		return datetime.strptime(value.strip(), '%Y-%m-%d').date(), None
	except (AttributeError, TypeError, ValueError):
		return None, {field_name: f"Invalid date format for '{field_name}'. Expected YYYY-MM-DD."}


def _generate_order_number():
	return f'MH-ORD-{uuid4().hex[:12].upper()}'


def _serialize_customer(customer):
	if customer is None:
		return None
	return {
		'id': customer.id,
		'email': customer.email,
		'username': customer.username,
		'full_name': customer.get_full_name(),
		'role': customer.role,
	}


def _serialize_item(item):
	return {
		'id': item.id,
		'product_id': item.product_id,
		'product_name_snapshot': item.product_name_snapshot,
		'sku_snapshot': item.sku_snapshot,
		'product_name': item.product_name_snapshot,
		'sku': item.sku_snapshot,
		'quantity': item.quantity,
		'unit_price': str(item.unit_price),
		'line_total': str(item.line_total),
	}


def _serialize_order(order, include_items=True):
	data = {
		'id': order.id,
		'order_number': order.order_number,
		'customer': _serialize_customer(order.customer),
		'status': order.status,
		'payment_method': order.payment_method,
		'payment_status': order.payment_status,
		'subtotal': str(order.subtotal),
		'discount': str(order.discount),
		'total': str(order.total),
		'notes': order.notes,
		'created_at': order.created_at.isoformat(),
		'updated_at': order.updated_at.isoformat(),
	}
	if include_items:
		data['items'] = [_serialize_item(item) for item in order.items.all()]
	return data


def _serialize_order_summary(order):
	data = _serialize_order(order, include_items=False)
	data['item_count'] = order.item_count
	return data


def _validation_response(errors):
	return _json_response(
		message='Validation failed.',
		success=False,
		status=400,
		errors=errors,
	)


def order_list(request):
	if request.method == 'POST':
		return order_create(request)
	if request.method != 'GET':
		return _json_response(message='Only GET and POST are allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_orders(request.user):
		return _json_response(message='You do not have permission to view orders.', success=False, status=403)

	orders = Order.objects.select_related('customer').annotate(item_count=Count('items'))
	if request.user.role == 'CUSTOMER':
		orders = orders.filter(customer=request.user)

	status_filter = (request.GET.get('status') or '').strip().upper()
	if status_filter:
		orders = orders.filter(status=status_filter)

	search = (request.GET.get('search') or '').strip()
	if search:
		orders = orders.filter(order_number__icontains=search)

	date_from, date_from_error = _parse_date(request.GET.get('date_from'), 'date_from')
	date_to, date_to_error = _parse_date(request.GET.get('date_to'), 'date_to')
	if date_from_error or date_to_error:
		errors = {}
		errors.update(date_from_error or {})
		errors.update(date_to_error or {})
		return _validation_response(errors)
	if date_from and date_to and date_from > date_to:
		return _validation_response({'date_from': 'date_from cannot be later than date_to.'})

	local_tz = timezone.get_current_timezone()
	if date_from:
		orders = orders.filter(
			created_at__gte=timezone.make_aware(datetime.combine(date_from, time.min), local_tz)
		)
	if date_to:
		orders = orders.filter(
			created_at__lte=timezone.make_aware(datetime.combine(date_to, time.max), local_tz)
		)

	allowed_ordering = {
		'order_number': 'order_number', '-order_number': '-order_number',
		'created_at': 'created_at', '-created_at': '-created_at',
		'total': 'total', '-total': '-total',
		'status': 'status', '-status': '-status',
	}
	ordering = (request.GET.get('ordering') or '-created_at').strip()
	orders = orders.order_by(allowed_ordering.get(ordering, '-created_at'), '-id')

	try:
		page = max(1, int(request.GET.get('page', 1)))
		page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
	except (TypeError, ValueError):
		page, page_size = 1, 10
	total_count = orders.count()
	start = (page - 1) * page_size
	items = list(orders[start:start + page_size])

	return _json_response(
		data={
			'orders': [_serialize_order_summary(order) for order in items],
			'pagination': {
				'total_count': total_count,
				'page': page,
				'page_size': page_size,
				'total_pages': (total_count + page_size - 1) // page_size,
			},
		},
		message='Orders retrieved successfully.',
	)


@transaction.atomic
def order_create(request):
	if request.method != 'POST':
		return _json_response(message='Only POST is allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if getattr(request.user, 'role', None) != 'CUSTOMER':
		return _json_response(message='Only customers can create orders.', success=False, status=403)

	payload, body_errors = _parse_json_body(request)
	if body_errors:
		return _validation_response(body_errors)

	item_payloads = payload.get('items')
	if not isinstance(item_payloads, list) or not item_payloads:
		return _validation_response({'items': 'At least one order item is required.'})
	notes = payload.get('notes', '')
	if notes is None:
		notes = ''
	if not isinstance(notes, str):
		return _validation_response({'notes': 'Notes must be text.'})

	payment_method = payload.get('payment_method', Order.PaymentMethod.CASH)
	if payment_method not in {choice.value for choice in Order.PaymentMethod}:
		return _validation_response({'payment_method': 'Invalid payment method.'})

	errors = {}
	prepared_items = []
	seen_products = set()
	subtotal = Decimal('0.00')
	for index, item_payload in enumerate(item_payloads):
		prefix = f'items[{index}]'
		if not isinstance(item_payload, dict):
			errors[prefix] = 'Item must be a JSON object.'
			continue
		product_id = item_payload.get('product_id')
		try:
			product = Product.objects.get(pk=product_id)
		except (Product.DoesNotExist, TypeError, ValueError):
			errors[f'{prefix}.product_id'] = 'Product not found.'
			continue
		if not product.is_active:
			errors[f'{prefix}.product_id'] = 'Product is inactive.'
			continue
		if product.id in seen_products:
			errors[f'{prefix}.product_id'] = 'Duplicate products are not allowed.'
			continue
		seen_products.add(product.id)
		try:
			quantity = _parse_positive_integer(item_payload.get('quantity'))
		except (TypeError, ValueError):
			errors[f'{prefix}.quantity'] = 'Quantity must be a positive integer.'
			continue
		prepared_items.append((product, quantity))
		subtotal += product.selling_price * quantity

	if errors:
		return _validation_response(errors)

	order = Order.objects.create(
		order_number=_generate_order_number(),
		customer=request.user,
		status=Order.OrderStatus.PENDING,
		payment_method=payment_method,
		discount=Decimal('0.00'),
		subtotal=subtotal,
		total=subtotal,
		notes=notes,
	)
	for product, quantity in prepared_items:
		OrderItem.create_from_product(product=product, order=order, quantity=quantity).save()

	order = Order.objects.select_related('customer').prefetch_related('items').get(pk=order.pk)
	return _json_response(
		data={'order': _serialize_order(order)},
		message='Order created successfully.',
		status=201,
	)


def order_detail(request, order_id):
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_orders(request.user):
		return _json_response(message='You do not have permission to view orders.', success=False, status=403)

	orders = Order.objects.select_related('customer').prefetch_related('items')
	if request.user.role == 'CUSTOMER':
		orders = orders.filter(customer=request.user)
	try:
		order = orders.get(pk=order_id)
	except Order.DoesNotExist:
		if request.user.role == 'CUSTOMER' and Order.objects.filter(pk=order_id).exists():
			return _json_response(message='You do not have permission to view this order.', success=False, status=403)
		return _json_response(message='Order not found.', success=False, status=404)

	return _json_response(
		data={'order': _serialize_order(order)},
		message='Order retrieved successfully.',
	)


@transaction.atomic
def order_status_update(request, order_id):
	if request.method != 'POST':
		return _json_response(message='Only POST is allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if getattr(request.user, 'role', None) not in MANAGEMENT_ROLES:
		return _json_response(message='You do not have permission to update order status.', success=False, status=403)

	try:
		order = Order.objects.select_related('customer').select_for_update().get(pk=order_id)
	except Order.DoesNotExist:
		return _json_response(message='Order not found.', success=False, status=404)

	payload, body_errors = _parse_json_body(request)
	if body_errors:
		return _validation_response(body_errors)
	new_status = payload.get('status')
	try:
		order.transition_to(new_status)
	except ValidationError as error:
		return _validation_response(error.message_dict)
	order.save(update_fields=['status', 'updated_at'])
	order = Order.objects.select_related('customer').prefetch_related('items').get(pk=order.pk)
	return _json_response(
		data={'order': _serialize_order(order)},
		message='Order status updated successfully.',
	)
