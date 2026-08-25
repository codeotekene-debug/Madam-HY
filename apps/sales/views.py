import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, Q, Sum, When, DecimalField, Value
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, time

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


def _can_view_sales(user):
	return bool(
		user
		and getattr(user, 'is_authenticated', False)
		and getattr(user, 'role', None) in ('OWNER', 'MANAGER', 'CASHIER', 'CUSTOMER')
	)


def _can_view_sales_dashboard(user):
	return bool(
		user
		and getattr(user, 'is_authenticated', False)
		and getattr(user, 'role', None) in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
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
		'product_name_snapshot': item.product_name_snapshot,
		'sku_snapshot': item.sku_snapshot,
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
		data['items'] = [_serialize_sale_item(item) for item in sale.items.all()]
	return data


def _validation_error_response(error):
	errors = error.message_dict if hasattr(error, 'message_dict') else {'detail': error.messages}
	return _json_response(message='Validation failed.', success=False, status=400, errors=errors)


def _parse_amount_received(payload, sale):
	method = sale.payment_method
	if method == Sale.PaymentMethod.CREDIT:
		return Decimal('0.00'), Decimal('0.00'), None

	if method == Sale.PaymentMethod.CASH and 'amount_received' not in payload:
		return None, None, {'amount_received': 'Amount received is required for cash payment.'}

	if method in (Sale.PaymentMethod.TRANSFER, Sale.PaymentMethod.CARD) and 'amount_received' not in payload:
		return sale.total, Decimal('0.00'), None

	try:
		amount_received = Decimal(str(payload.get('amount_received')))
	except (InvalidOperation, TypeError, ValueError):
		return None, None, {'amount_received': 'Payment amount is invalid.'}

	if not amount_received.is_finite() or amount_received < 0:
		return None, None, {'amount_received': 'Payment amount must be non-negative.'}
	if amount_received.as_tuple().exponent < -2:
		return None, None, {'amount_received': 'Payment amount cannot have more than two decimal places.'}

	if method == Sale.PaymentMethod.CASH:
		if amount_received < sale.total:
			return None, None, {'amount_received': 'Amount received cannot be less than the sale total.'}
		return amount_received, amount_received - sale.total, None

	if amount_received != sale.total:
		return None, None, {'amount_received': 'Payment amount must equal the sale total.'}
	return sale.total, Decimal('0.00'), None


def _parse_date(value, field_name):

	if not value:
		return None, None
	try:
		return datetime.strptime(value.strip(), '%Y-%m-%d').date(), None
	except (AttributeError, TypeError, ValueError):
		return None, {field_name: f"Invalid date format for '{field_name}'. Expected YYYY-MM-DD."}


def _serialize_sale_list_item(sale):
	return {
		'id': sale.id,
		'sale_id': sale.id,
		'sale_number': sale.sale_number,
		'customer': _serialize_customer(sale.customer),
		'cashier': _serialize_customer(sale.cashier),
		'status': sale.status,
		'payment_method': sale.payment_method,
		'payment_status': sale.payment_status,
		'subtotal': str(sale.subtotal),
		'discount': str(sale.discount),
		'total': str(sale.total),
		'amount_received': str(sale.amount_received) if sale.amount_received is not None else None,
		'change_amount': str(sale.change_amount) if sale.change_amount is not None else None,
		'created_at': sale.created_at.isoformat(),
		'updated_at': sale.updated_at.isoformat(),
	}


def sale_list(request):
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_sales(request.user):
		return _json_response(message='You do not have permission to view sales.', success=False, status=403)

	sales = Sale.objects.select_related('customer', 'cashier')
	if getattr(request.user, 'role', None) == 'CUSTOMER':
		sales = sales.filter(customer=request.user)
	search = (request.GET.get('search') or '').strip()
	if search:
		sales = sales.filter(
			Q(sale_number__icontains=search)
			| Q(customer__first_name__icontains=search)
			| Q(customer__last_name__icontains=search)
			| Q(customer__username__icontains=search)
			| Q(customer__email__icontains=search)
			| Q(cashier__first_name__icontains=search)
			| Q(cashier__last_name__icontains=search)
			| Q(cashier__username__icontains=search)
		)

	for field in ('status', 'payment_method', 'payment_status'):
		value = (request.GET.get(field) or '').strip().upper()
		if value:
			sales = sales.filter(**{field: value})

	cashier_id = (request.GET.get('cashier_id') or '').strip()
	if cashier_id:
		try:
			sales = sales.filter(cashier_id=int(cashier_id))
		except ValueError:
			return _json_response(message='Validation failed.', success=False, status=400, errors={'cashier_id': 'Cashier ID must be numeric.'})

	date_from, date_from_error = _parse_date(request.GET.get('date_from'), 'date_from')
	date_to, date_to_error = _parse_date(request.GET.get('date_to'), 'date_to')
	if date_from_error or date_to_error:
		errors = {}
		errors.update(date_from_error or {})
		errors.update(date_to_error or {})
		return _json_response(message='Validation failed.', success=False, status=400, errors=errors)
	if date_from and date_to and date_from > date_to:
		return _json_response(message='Validation failed.', success=False, status=400, errors={'date_from': 'date_from cannot be later than date_to.'})
	local_tz = timezone.get_current_timezone()
	if date_from:
		sales = sales.filter(created_at__gte=timezone.make_aware(datetime.combine(date_from, time.min), local_tz))
	if date_to:
		sales = sales.filter(created_at__lte=timezone.make_aware(datetime.combine(date_to, time.max), local_tz))

	ordering = (request.GET.get('ordering') or '-created_at').strip()
	allowed_ordering = {
		'sale_number': 'sale_number', '-sale_number': '-sale_number',
		'created_at': 'created_at', '-created_at': '-created_at',
		'total': 'total', '-total': '-total',
		'status': 'status', '-status': '-status',
	}
	sales = sales.order_by(allowed_ordering.get(ordering, '-created_at'), '-id')
	try:
		page = max(1, int(request.GET.get('page', 1)))
		page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
	except (TypeError, ValueError):
		page, page_size = 1, 10
	total_count = sales.count()
	start = (page - 1) * page_size
	items = list(sales[start:start + page_size])
	return _json_response(
		data={
			'sales': [_serialize_sale_list_item(sale) for sale in items],
			'pagination': {
				'total_count': total_count,
				'page': page,
				'page_size': page_size,
				'total_pages': (total_count + page_size - 1) // page_size,
			},
		},
		message='Sales retrieved successfully.',
	)


def sale_detail(request, sale_id):
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_sales(request.user):
		return _json_response(message='You do not have permission to view sales.', success=False, status=403)
	try:
		queryset = Sale.objects.select_related('customer', 'cashier').prefetch_related('items')
		if getattr(request.user, 'role', None) == 'CUSTOMER':
			queryset = queryset.filter(customer=request.user)
		sale = queryset.get(pk=sale_id)
	except Sale.DoesNotExist:
		if getattr(request.user, 'role', None) == 'CUSTOMER':
			return _json_response(message='You do not have permission to view this sale.', success=False, status=403)
		return _json_response(message='Sale not found.', success=False, status=404)
	return _json_response(data=_serialize_sale(sale), message='Sale retrieved successfully.')


def sale_report_summary(request):
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_sales_dashboard(request.user):
		return _json_response(message='You do not have permission to view the sales dashboard.', success=False, status=403)

	date_from, date_from_error = _parse_date(request.GET.get('date_from'), 'date_from')
	date_to, date_to_error = _parse_date(request.GET.get('date_to'), 'date_to')
	if date_from_error or date_to_error:
		errors = {}
		errors.update(date_from_error or {})
		errors.update(date_to_error or {})
		return _json_response(message='Validation failed.', success=False, status=400, errors=errors)
	if date_from and date_to and date_from > date_to:
		return _json_response(message='Validation failed.', success=False, status=400, errors={'date_from': 'date_from cannot be later than date_to.'})

	sales = Sale.objects.filter(status=Sale.SaleStatus.COMPLETED)
	local_tz = timezone.get_current_timezone()
	if date_from:
		sales = sales.filter(created_at__gte=timezone.make_aware(datetime.combine(date_from, time.min), local_tz))
	if date_to:
		sales = sales.filter(created_at__lte=timezone.make_aware(datetime.combine(date_to, time.max), local_tz))

	zero = Value(Decimal('0.00'), output_field=DecimalField(max_digits=14, decimal_places=2))
	aggregates = sales.aggregate(
		total_sales=Sum('total', default=Decimal('0.00')),
		transaction_count=Count('id'),
		total_discount=Sum('discount', default=Decimal('0.00')),
		cash_total=Sum(Case(When(payment_method=Sale.PaymentMethod.CASH, then='total'), default=zero, output_field=DecimalField(max_digits=14, decimal_places=2))),
		transfer_total=Sum(Case(When(payment_method=Sale.PaymentMethod.TRANSFER, then='total'), default=zero, output_field=DecimalField(max_digits=14, decimal_places=2))),
		card_total=Sum(Case(When(payment_method=Sale.PaymentMethod.CARD, then='total'), default=zero, output_field=DecimalField(max_digits=14, decimal_places=2))),
		credit_total=Sum(Case(When(payment_method=Sale.PaymentMethod.CREDIT, then='total'), default=zero, output_field=DecimalField(max_digits=14, decimal_places=2))),
	)
	return _json_response(
		data={
			'total_sales': str(aggregates['total_sales'] or Decimal('0.00')),
			'transaction_count': aggregates['transaction_count'] or 0,
			'total_discount': str(aggregates['total_discount'] or Decimal('0.00')),
			'cash_total': str(aggregates['cash_total'] or Decimal('0.00')),
			'transfer_total': str(aggregates['transfer_total'] or Decimal('0.00')),
			'card_total': str(aggregates['card_total'] or Decimal('0.00')),
			'credit_total': str(aggregates['credit_total'] or Decimal('0.00')),
		},
		message='Sales summary retrieved successfully.',
	)


def sale_create(request):
	if request.method == 'GET':
		return sale_list(request)
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

	payload, body_errors = _parse_json_body(request)
	if body_errors:
		return _json_response(message='Validation failed.', success=False, status=400, errors=body_errors)
	amount_received, change_amount, payment_error = _parse_amount_received(payload, sale)
	if payment_error:
		return _json_response(message='Validation failed.', success=False, status=400, errors=payment_error)

	try:
		sale.amount_received = amount_received
		sale.change_amount = change_amount
		sale.save(update_fields=['amount_received', 'change_amount', 'updated_at'])
		sale.complete_sale()
	except ValidationError as error:
		transaction.set_rollback(True)
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
