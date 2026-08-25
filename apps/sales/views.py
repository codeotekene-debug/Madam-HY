import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse

from apps.products.models import Product
from .models import Sale, SaleItem

User = get_user_model()


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
	payload = {'success': success, 'message': message}
	if data is not None:
		payload['data'] = data
	if errors is not None:
		payload['errors'] = errors
	return JsonResponse(payload, status=status)


def _can_process_sales(user):
	return bool(
		user
		and getattr(user, 'is_authenticated', False)
		and getattr(user, 'role', None) in ('OWNER', 'MANAGER', 'CASHIER')
	)


def _parse_json_body(request):
	try:
		payload = json.loads(request.body or '{}')
	except (TypeError, ValueError):
		return None, {'body': 'Request body must be valid JSON.'}
	if not isinstance(payload, dict):
		return None, {'body': 'Request body must be a JSON object.'}
	return payload, None


def _parse_money(value, field_name, default=None):
	if value is None and default is not None:
		return default, None
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError):
		return None, {field_name: 'Must be a valid monetary amount.'}
	if not amount.is_finite() or amount < 0:
		return None, {field_name: 'Must be a non-negative monetary amount.'}
	return amount, None


def _parse_positive_integer(value):
	if isinstance(value, bool):
		raise ValueError
	quantity = int(value)
	if str(value).strip() != str(quantity) or quantity <= 0:
		raise ValueError
	return quantity


def _generate_sale_number():
	return f'MH-{uuid4().hex[:12].upper()}'


def _serialize_customer(customer):
	if customer is None:
		return None
	return {
		'id': customer.id,
		'email': customer.email,
		'username': customer.username,
		'full_name': customer.get_full_name(),
	}


def _serialize_sale_item(item):
	return {
		'id': item.id,
		'product_id': item.product_id,
		'product_name': item.product_name_snapshot,
		'sku': item.sku_snapshot,
		'quantity': item.quantity,
		'unit_price': str(item.unit_price),
		'discount': str(item.discount),
		'line_total': str(item.line_total),
	}


def _serialize_sale(sale, include_items=True):
	data = {
		'id': sale.id,
		'sale_number': sale.sale_number,
		'status': sale.status,
		'payment_status': sale.payment_status,
		'subtotal': str(sale.subtotal),
		'discount': str(sale.discount),
		'total': str(sale.total),
		'amount_received': str(sale.amount_received) if sale.amount_received is not None else None,
		'change_amount': str(sale.change_amount) if sale.change_amount is not None else None,
		'payment_method': sale.payment_method,
		'customer': _serialize_customer(sale.customer),
		'cashier_id': sale.cashier_id,
		'notes': sale.notes,
		'created_at': sale.created_at.isoformat(),
		'updated_at': sale.updated_at.isoformat(),
	}
	if include_items:
		data['items'] = [_serialize_sale_item(item) for item in sale.items.select_related('product').all()]
	return data


def _validation_error_response(error):
	errors = error.message_dict if hasattr(error, 'message_dict') else {'detail': error.messages}
	return _json_response(message='Validation failed.', success=False, status=400, errors=errors)


def sale_create(request):
	if request.method != 'POST':
		return _json_response(message='Only POST is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_process_sales(request.user):
		return _json_response(message='You do not have permission to create sales.', success=False, status=403)

	payload, errors = _parse_json_body(request)
	if errors:
		return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

	payment_method = payload.get('payment_method')
	valid_payment_methods = {choice.value for choice in Sale.PaymentMethod}
	if payment_method not in valid_payment_methods:
		errors = {'payment_method': 'Invalid payment method.'}
	else:
		errors = {}

	items_payload = payload.get('items')
	if not isinstance(items_payload, list) or not items_payload:
		errors['items'] = 'At least one sale item is required.'

	discount, discount_error = _parse_money(payload.get('discount', '0.00'), 'discount', Decimal('0.00'))
	if discount_error:
		errors.update(discount_error)

	customer = None
	customer_id = payload.get('customer_id')
	if customer_id is not None:
		try:
			customer = User.objects.get(pk=customer_id, role='CUSTOMER')
		except (User.DoesNotExist, TypeError, ValueError):
			errors['customer_id'] = 'Customer not found.'

	if payment_method == Sale.PaymentMethod.CREDIT and customer is None:
		errors['customer_id'] = 'Customer is required for credit sales.'

	prepared_items = []
	subtotal = Decimal('0.00')
	for index, item_payload in enumerate(items_payload if isinstance(items_payload, list) else []):
		prefix = f'items[{index}]'
		if not isinstance(item_payload, dict):
			errors[prefix] = 'Item must be a JSON object.'
			continue

		try:
			product = Product.objects.select_related('inventory_item').get(pk=item_payload.get('product_id'))
		except (Product.DoesNotExist, TypeError, ValueError):
			errors[f'{prefix}.product_id'] = 'Product not found.'
			continue

		if not product.is_active:
			errors[f'{prefix}.product_id'] = 'Product is inactive.'
			continue
		if not hasattr(product, 'inventory_item'):
			errors[f'{prefix}.product_id'] = 'Product does not have inventory tracking.'
			continue

		try:
			quantity = _parse_positive_integer(item_payload.get('quantity'))
		except (TypeError, ValueError):
			errors[f'{prefix}.quantity'] = 'Quantity must be a positive integer.'
			continue

		line_discount, line_discount_error = _parse_money(
			item_payload.get('discount', '0.00'),
			f'{prefix}.discount',
			Decimal('0.00'),
		)
		if line_discount_error:
			errors.update(line_discount_error)
			continue

		line_gross = product.selling_price * quantity
		if line_discount > line_gross:
			errors[f'{prefix}.discount'] = 'Line discount cannot exceed the line total.'
			continue

		line_total = line_gross - line_discount
		subtotal += line_total
		prepared_items.append((product, quantity, line_discount))

	if errors:
		return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

	sale = Sale(
		sale_number=_generate_sale_number(),
		customer=customer,
		cashier=request.user,
		status=Sale.SaleStatus.DRAFT,
		payment_method=payment_method,
		discount=discount,
		subtotal=subtotal,
		total=max(subtotal - discount, Decimal('0.00')),
		notes=payload.get('notes') or '',
	)
	try:
		with transaction.atomic():
			sale.save()
			for product, quantity, line_discount in prepared_items:
				SaleItem.create_from_product(
					product=product,
					sale=sale,
					quantity=quantity,
					discount=line_discount,
				).save()
	except ValidationError as error:
		return _validation_error_response(error)

	sale.refresh_from_db()
	return _json_response(
		data={
			'sale': _serialize_sale(sale, include_items=False),
			'items': [_serialize_sale_item(item) for item in sale.items.select_related('product').all()],
		},
		message='Draft sale created successfully.',
	)


@transaction.atomic
def sale_complete(request, sale_id):
	if request.method != 'POST':
		return _json_response(message='Only POST is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_process_sales(request.user):
		return _json_response(message='You do not have permission to complete sales.', success=False, status=403)

	try:
		sale = Sale.objects.select_related('customer', 'cashier').prefetch_related('items__product').get(pk=sale_id)
	except Sale.DoesNotExist:
		return _json_response(message='Sale not found.', success=False, status=404)

	if sale.status != Sale.SaleStatus.DRAFT:
		return _json_response(message='Only DRAFT sales can be completed.', success=False, status=409)

	try:
		sale.complete_sale()
	except ValidationError as error:
		return _validation_error_response(error)

	sale.refresh_from_db()
	return _json_response(
		data={
			'sale_number': sale.sale_number,
			'status': sale.status,
			'payment_status': sale.payment_status,
			'subtotal': str(sale.subtotal),
			'discount': str(sale.discount),
			'total': str(sale.total),
			'amount_received': str(sale.amount_received) if sale.amount_received is not None else None,
			'change_amount': str(sale.change_amount) if sale.change_amount is not None else None,
			'payment_method': sale.payment_method,
			'customer': _serialize_customer(sale.customer),
			'items': [_serialize_sale_item(item) for item in sale.items.select_related('product').all()],
			'completed_at': sale.updated_at.isoformat(),
		},
		message='Sale completed successfully.',
	)

# Create your views here.
