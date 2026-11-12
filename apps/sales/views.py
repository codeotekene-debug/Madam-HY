import json
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, Q, Sum, When, DecimalField, Value
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, time

from apps.products.models import Product
from .dashboard_service import ManagementDashboardService
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

	if not _wants_json(request):
		if not request.user or not getattr(request.user, 'is_authenticated', False):
			return redirect(f"{reverse('accounts:login')}?next=/sales/summary/")
		if getattr(request.user, 'role', None) == 'CUSTOMER':
			return redirect('/customer/dashboard/')
		if not _can_view_sales_dashboard(request.user):
			return render(request, '403.html', {'message': 'You do not have permission to view sales reports.'}, status=403)
		return render(request, 'sales/dashboard.html', {})

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
			'total_sales': f"{Decimal(str(aggregates['total_sales'] or 0)):.2f}",
			'transaction_count': aggregates['transaction_count'] or 0,
			'total_discount': f"{Decimal(str(aggregates['total_discount'] or 0)):.2f}",
			'cash_total': f"{Decimal(str(aggregates['cash_total'] or 0)):.2f}",
			'transfer_total': f"{Decimal(str(aggregates['transfer_total'] or 0)):.2f}",
			'card_total': f"{Decimal(str(aggregates['card_total'] or 0)):.2f}",
			'credit_total': f"{Decimal(str(aggregates['credit_total'] or 0)):.2f}",
		},
		message='Sales summary retrieved successfully.',
	)


def sale_create(request):
	if request.method == 'GET':
		if not _wants_json(request):
			return redirect('sales:pos')
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

		if product.inventory_item.quantity < quantity:
			errors[f'{prefix}.quantity'] = f'Insufficient stock. Only {product.inventory_item.quantity} units available.'
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
		if product.cost_price is not None and product.cost_price > Decimal('0.00'):
			min_line_total = product.cost_price * quantity
			if line_total < min_line_total:
				errors[f'{prefix}.discount'] = (
					f'Line discount causes effective selling price to fall below cost price '
					f'({product.cost_price:.2f} per unit).'
				)
				continue

		subtotal += line_total
		prepared_items.append((product, quantity, line_discount))

	total_cost = sum(
		((p.cost_price or Decimal('0.00')) * q)
		for p, q, _ in prepared_items
	)
	effective_discount = discount if discount is not None else Decimal('0.00')
	if effective_discount > Decimal('0.00') and total_cost > Decimal('0.00') and (subtotal - effective_discount) < total_cost:
		errors['discount'] = 'Sale discount causes effective sale total to fall below total product cost price.'

	if errors:
		return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

	final_sale_total = max(subtotal - effective_discount, Decimal('0.00'))
	if payment_method == Sale.PaymentMethod.CREDIT and customer is not None:
		from apps.credits.services import CreditService
		try:
			CreditService.validate_credit_eligibility(customer, final_sale_total)
		except ValidationError as credit_err:
			credit_errors = credit_err.message_dict if hasattr(credit_err, 'message_dict') else {'credit': credit_err.messages}
			return _json_response(message='Validation failed.', success=False, status=400, errors=credit_errors)

	sale = Sale(
		sale_number=_generate_sale_number(),
		customer=customer,
		cashier=request.user,
		status=Sale.SaleStatus.DRAFT,
		payment_method=payment_method,
		discount=discount,
		subtotal=subtotal,
		total=final_sale_total,
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
	response_data = {
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
	}

	if sale.payment_method == Sale.PaymentMethod.CREDIT and sale.customer:
		try:
			account = getattr(sale.customer, 'credit_account', None)
			if account:
				account.refresh_from_db()
				response_data['credit_account'] = {
					'outstanding_balance': str(account.outstanding_balance),
					'current_balance': str(account.outstanding_balance),
					'credit_limit': str(account.credit_limit),
					'available_credit': str(account.get_available_credit()),
					'status': account.status,
				}
		except Exception:
			pass

	return _json_response(
		data=response_data,
		message='Sale completed successfully.',
	)


def customer_search_view(request):
	"""Customer search endpoint for POS Credit Ledger and counter lookup."""
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)
	if not request.user or not getattr(request.user, 'is_authenticated', False):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_process_sales(request.user):
		return _json_response(message='You do not have permission to search customers.', success=False, status=403)

	query = (request.GET.get('q') or request.GET.get('search') or '').strip()
	customers_qs = User.objects.filter(role='CUSTOMER', is_active=True)
	if query:
		customers_qs = customers_qs.filter(
			Q(first_name__icontains=query)
			| Q(last_name__icontains=query)
			| Q(phone_number__icontains=query)
			| Q(email__icontains=query)
			| Q(username__icontains=query)
		)

	customers_qs = customers_qs.select_related('credit_account').order_by('first_name', 'last_name')[:20]

	results = []
	for cust in customers_qs:
		credit_acc = getattr(cust, 'credit_account', None)
		if credit_acc:
			available = credit_acc.get_available_credit()
			limit = credit_acc.credit_limit
			balance = credit_acc.outstanding_balance
			status = credit_acc.status
			has_account = True
			can_use = credit_acc.can_use_credit(1)
		else:
			available = Decimal('0.00')
			limit = Decimal('0.00')
			balance = Decimal('0.00')
			status = 'NO_ACCOUNT'
			has_account = False
			can_use = False

		results.append({
			'id': cust.id,
			'name': cust.get_full_name() or cust.username,
			'full_name': cust.get_full_name() or cust.username,
			'username': cust.username,
			'phone': getattr(cust, 'phone_number', '') or '',
			'email': cust.email,
			'credit_limit': str(limit),
			'outstanding_balance': str(balance),
			'current_balance': str(balance),
			'available_credit': str(available),
			'has_credit_account': has_account,
			'status': status,
			'can_use_credit': can_use,
		})

	return _json_response(data={'customers': results}, message='Customers retrieved successfully.')


def pos_view(request):
	"""Interactive POS Cashier Register View (GET /sales/pos/)."""
	if not request.user or not request.user.is_authenticated:
		return redirect(f"{reverse('accounts:login')}?next=/sales/pos/")
	if not _can_process_sales(request.user):
		if _wants_json(request):
			return _json_response(message="You do not have permission to access the POS terminal.", success=False, status=403)
		from django.contrib import messages
		messages.warning(request, "Access restricted to store staff. Redirected to customer storefront.")
		return redirect('/customer/products/')
	from django.conf import settings
	context = {
		'counter_account': getattr(settings, 'MONIEPOINT_COUNTER_ACCOUNT', '') or '8123456789',
		'bank_name': getattr(settings, 'MONIEPOINT_BANK_NAME', 'Moniepoint MFB'),
		'terminal_serial': getattr(settings, 'MONIEPOINT_TERMINAL_ID', '') or 'MP_POS_01',
	}
	return render(request, 'sales/pos.html', context)


def sales_checkout_view(request):
	"""Sales Checkout View (GET /sales/checkout/)."""
	if not request.user or not request.user.is_authenticated:
		return redirect(f"{reverse('accounts:login')}?next=/sales/checkout/")
	if not _can_process_sales(request.user):
		if _wants_json(request):
			return _json_response(message="You do not have permission to access sales checkout.", success=False, status=403)
		return redirect('sales:dashboard')
	return render(request, 'sales/checkout.html', {})


def sales_receipt_view(request):
	"""Sales Receipt View (GET /sales/receipt/)."""
	if not request.user or not request.user.is_authenticated:
		return redirect(f"{reverse('accounts:login')}?next=/sales/receipt/")
	if not _can_view_sales(request.user):
		if _wants_json(request):
			return _json_response(message="You do not have permission to view receipts.", success=False, status=403)
		return redirect('sales:dashboard')
	return render(request, 'sales/receipt.html', {})


def sales_history_view(request):
	"""Completed Sales Transactions Audit History View (GET /sales/history/)."""
	if not request.user or not request.user.is_authenticated:
		return redirect(f"{reverse('accounts:login')}?next=/sales/history/")
	if not _can_view_sales(request.user):
		if _wants_json(request):
			return _json_response(message="You do not have permission to view sales history.", success=False, status=403)
		return redirect('sales:dashboard')
	return render(request, 'sales/sales_history.html', {})



def management_dashboard_view(request):
	"""Unified Management Dashboard View (GET /dashboard/).

	Routes OWNER and MANAGER roles to owner.html with business analytics,
	and CASHIER and STAFF roles to staff.html with operational work queues.
	Enforces strict role boundaries and customer isolation.
	"""
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)

	accept = request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')
	wants_json = (
		request.GET.get('format') == 'json'
		or ('application/json' in accept and 'text/html' not in accept)
		or request.headers.get('x-requested-with') == 'XMLHttpRequest'
	)

	if not request.user or not request.user.is_authenticated:
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		return redirect(f"{reverse('accounts:login')}?next=/dashboard/")

	user_role = getattr(request.user, 'role', None)

	if user_role == 'CUSTOMER':
		if wants_json:
			return _json_response(message='Customers cannot access the management dashboard.', success=False, status=403)
		return redirect('/customer/dashboard/')

	if user_role not in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
		if wants_json:
			return _json_response(message='Access denied.', success=False, status=403)
		return redirect(f"{reverse('accounts:login')}?next=/dashboard/")

	if user_role in ('OWNER', 'MANAGER'):
		dashboard_data = ManagementDashboardService.get_owner_dashboard_data()
		template_name = 'dashboard/owner.html'
	else:
		dashboard_data = ManagementDashboardService.get_staff_dashboard_data(request.user)
		template_name = 'dashboard/staff.html'

	if wants_json:
		return _json_response(
			data=dashboard_data,
			message=f"{dashboard_data['role'].capitalize()} dashboard retrieved successfully.",
			success=True,
			status=200,
		)

	context = {
		**dashboard_data,
		'dashboard_json': json.dumps(dashboard_data),
	}
	return render(request, template_name, context)
