import json
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.products.models import Product
from apps.products.views import customer_product_detail, customer_product_list
from apps.sales.models import Sale, SaleItem
from apps.delivery.models import DeliveryZone

from .cart import CustomerCart
from .models import Order, OrderItem


MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
User = get_user_model()


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
		'created_by': _serialize_customer(order.created_by),
		'status': order.status,
		'payment_method': order.payment_method,
		'payment_status': order.payment_status,
		'subtotal': str(order.subtotal),
		'discount': str(order.discount),
		'total': str(order.total),
		'notes': order.notes,
		'delivery_address': order.delivery_address,
		'customer_phone': order.customer_phone,
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


def _order_action_url(order):
	return f'/orders/{order.pk}/'


def _notify_order_recipients(order, title, message, priority=Notification.Priority.NORMAL, recipients=None):
	for recipient in recipients if recipients is not None else User.objects.filter(
		role__in=MANAGEMENT_ROLES,
		is_active=True,
	):
		create_notification(
			recipient=recipient,
			notification_type=Notification.NotificationType.ORDER,
			title=title,
		message=message,
		priority=priority,
		related_object=order,
		action_url=_order_action_url(order),
		)


def order_list(request):
	if request.method == 'GET' and not _wants_json(request):
		if not _is_authenticated(request.user):
			return redirect(f"{reverse('accounts:login')}?next={request.path}")
		if getattr(request.user, 'role', None) == 'CUSTOMER':
			return render(request, 'customer/orders.html', {})
		if not _can_view_orders(request.user):
			return redirect(f"{reverse('accounts:login')}?next={request.path}")
		status_param = (request.GET.get('status') or '').strip().upper()
		active_tab = 'pending' if status_param == 'PENDING' else ('completed' if status_param in ('FULFILLED', 'COMPLETED') else 'all')
		return render(request, 'orders/orders.html', {
			'active_module': 'orders',
			'active_tab': active_tab,
		})

	if request.method == 'POST':
		return order_create(request)
	if request.method != 'GET':
		return _json_response(message='Only GET and POST are allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_orders(request.user):
		return _json_response(message='You do not have permission to view orders.', success=False, status=403)

	orders = Order.objects.select_related('customer', 'created_by').annotate(item_count=Count('items'))
	if request.user.role == 'CUSTOMER':
		orders = orders.filter(customer=request.user)

	status_filter = (request.GET.get('status') or '').strip().upper()
	if status_filter:
		orders = orders.filter(status=status_filter)

	payment_method = (request.GET.get('payment_method') or '').strip().upper()
	if payment_method:
		orders = orders.filter(payment_method=payment_method)

	customer_filter = (request.GET.get('customer') or '').strip()
	if customer_filter and request.user.role != 'CUSTOMER':
		try:
			orders = orders.filter(customer_id=int(customer_filter))
		except ValueError:
			return _validation_response({'customer': 'Customer ID must be numeric.'})

	search = (request.GET.get('search') or '').strip()
	if search:
		orders = orders.filter(
			Q(order_number__icontains=search)
			| Q(customer__first_name__icontains=search)
			| Q(customer__last_name__icontains=search)
			| Q(customer__username__icontains=search)
			| Q(customer__email__icontains=search)
		)

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

def order_summary(request):
    if request.method != 'GET':
        return _json_response(
            message='Only GET is allowed.',
            success=False,
            status=405,
        )

    if not _is_authenticated(request.user):
        if not _wants_json(request):
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        return _json_response(
            message='Authentication required.',
            success=False,
            status=401,
        )

    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        if not _wants_json(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have permission to view order summary.')
        return _json_response(
            message='You do not have permission to view order summary.',
            success=False,
            status=403,
        )

    orders = Order.objects.all()

    status_filter = (request.GET.get('status') or '').strip().upper()
    if status_filter:
        orders = orders.filter(status=status_filter)

    payment_method = (
        request.GET.get('payment_method') or ''
    ).strip().upper()

    if payment_method:
        orders = orders.filter(payment_method=payment_method)

    customer_filter = (request.GET.get('customer') or '').strip()

    if customer_filter:
        try:
            customer_id = int(customer_filter)
        except (TypeError, ValueError):
            return _validation_response({
                'customer': 'Customer ID must be numeric.'
            })

        orders = orders.filter(customer_id=customer_id)

    search = (request.GET.get('search') or '').strip()

    if search:
        orders = orders.filter(
            Q(order_number__icontains=search)
            | Q(customer__first_name__icontains=search)
            | Q(customer__last_name__icontains=search)
            | Q(customer__username__icontains=search)
            | Q(customer__email__icontains=search)
        )

    date_from, date_from_error = _parse_date(
        request.GET.get('date_from'),
        'date_from',
    )

    date_to, date_to_error = _parse_date(
        request.GET.get('date_to'),
        'date_to',
    )

    if date_from_error or date_to_error:
        errors = {}
        errors.update(date_from_error or {})
        errors.update(date_to_error or {})

        return _validation_response(errors)

    if date_from and date_to and date_from > date_to:
        return _validation_response({
            'date_from': 'date_from cannot be later than date_to.'
        })

    local_tz = timezone.get_current_timezone()

    if date_from:
        orders = orders.filter(
            created_at__gte=timezone.make_aware(
                datetime.combine(date_from, time.min),
                local_tz,
            )
        )

    if date_to:
        orders = orders.filter(
            created_at__lte=timezone.make_aware(
                datetime.combine(date_to, time.max),
                local_tz,
            )
        )

    completed_orders = orders.filter(
        status=Order.OrderStatus.COMPLETED
    )

    totals = orders.aggregate(
        total_orders=Count('id'),
        total_discount=Sum('discount'),
    )

    completed_totals = completed_orders.aggregate(
        completed_orders=Count('id'),
        total_revenue=Sum('total'),
    )

    payment_totals = {
        method.value: completed_orders.filter(
            payment_method=method.value
        ).aggregate(
            total=Sum('total')
        )['total'] or Decimal('0.00')
        for method in Order.PaymentMethod
    }

    completed_count = completed_totals['completed_orders'] or 0
    revenue = completed_totals['total_revenue'] or Decimal('0.00')

    average_order_value = (
        revenue / completed_count
        if completed_count
        else Decimal('0.00')
    )

    summary_data = {
        'total_orders': totals['total_orders'] or 0,
        'completed_orders': completed_count,
        'cancelled_orders': orders.filter(
            status=Order.OrderStatus.CANCELLED
        ).count(),
        'total_discount': str(
            totals['total_discount'] or Decimal('0.00')
        ),
        'total_revenue': str(revenue),
        'average_order_value': str(
            average_order_value.quantize(Decimal('0.01'))
        ),
        'payment_totals': {
            key: str(value)
            for key, value in payment_totals.items()
        },
    }

    if not _wants_json(request):
        return render(request, 'orders/order_summary.html', {
            'active_module': 'orders',
            'active_tab': 'summary',
            'summary': summary_data,
        })

    return _json_response(
        data=summary_data,
        message='Order summary retrieved successfully.',
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

	if payment_method == Order.PaymentMethod.CASH:
		allow_cod = all(getattr(product, 'allow_pay_on_delivery', True) for product, _ in prepared_items) if prepared_items else True
		if not allow_cod:
			return _validation_response({'payment_method': 'Requires upfront online payment'})

	if payment_method == Order.PaymentMethod.CREDIT:
		from apps.credits.services import CreditService
		try:
			CreditService.validate_credit_eligibility(request.user, subtotal)
		except ValidationError as credit_error:
			credit_errors = credit_error.message_dict if hasattr(credit_error, 'message_dict') else {'credit': credit_error.messages}
			return _validation_response(credit_errors)

	try:
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
	except ValidationError as error:
		return _validation_response(error.message_dict if hasattr(error, 'message_dict') else {'detail': error.messages})

	_notify_order_recipients(
		order,
		title='New customer order',
		message=f'{order.order_number} was placed and is pending review.',
		priority=Notification.Priority.HIGH,
	)

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
		if not _wants_json(request):
			return redirect(f"{reverse('accounts:login')}?next={request.path}")
		return _json_response(message='Authentication required.', success=False, status=401)
	if not _can_view_orders(request.user):
		if not _wants_json(request):
			from django.core.exceptions import PermissionDenied
			raise PermissionDenied('You do not have permission to view orders.')
		return _json_response(message='You do not have permission to view orders.', success=False, status=403)

	orders = Order.objects.select_related('customer', 'created_by').prefetch_related('items')
	if request.user.role == 'CUSTOMER':
		orders = orders.filter(customer=request.user)
	try:
		order = orders.get(pk=order_id)
	except Order.DoesNotExist:
		if request.user.role == 'CUSTOMER' and Order.objects.filter(pk=order_id).exists():
			return _json_response(message='You do not have permission to view this order.', success=False, status=403)
		if not _wants_json(request):
			from django.http import Http404
			raise Http404('Order not found.')
		return _json_response(message='Order not found.', success=False, status=404)

	serialized_order = _serialize_order(order)
	if not _wants_json(request):
		template_name = 'customer/order_detail.html' if request.user.role == 'CUSTOMER' else 'orders/order_detail.html'
		return render(request, template_name, {
			'order': order,
			'order_data': serialized_order,
			'active_module': 'orders',
			'active_tab': 'all',
		})

	return _json_response(
		data={'order': serialized_order},
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
	if new_status == Order.OrderStatus.CONFIRMED and order.delivery_zone_id:
		try:
			from apps.delivery.services import DeliveryService
			DeliveryService.create_delivery_for_order(order, created_by=request.user)
		except Exception:
			transaction.set_rollback(True)
			return _json_response(message='Order was not confirmed because its delivery record could not be created.', success=False, status=400)
	_notify_order_recipients(
		order,
		title='Order status updated',
		message=f'{order.order_number} is now {order.get_status_display()}.',
		recipients=[order.customer] if order.customer_id else [],
	)
	order = Order.objects.select_related('customer').prefetch_related('items').get(pk=order.pk)
	return _json_response(
		data={'order': _serialize_order(order)},
		message='Order status updated successfully.',
	)


def _serialize_converted_sale(sale):
	return {
		'id': sale.id,
		'sale_number': sale.sale_number,
		'status': sale.status,
		'payment_status': sale.payment_status,
		'customer_id': sale.customer_id,
		'source_order_id': sale.source_order_id,
		'subtotal': str(sale.subtotal),
		'discount': str(sale.discount),
		'total': str(sale.total),
	}


@transaction.atomic
def order_convert_to_sale(request, order_id):
	if request.method != 'POST':
		return _json_response(message='Only POST is allowed.', success=False, status=405)
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)
	if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER', 'CASHIER'):
		return _json_response(message='You do not have permission to convert orders to sales.', success=False, status=403)

	try:
		order = (
			Order.objects.select_for_update()
			.select_related('customer')
			.prefetch_related('items')
			.get(pk=order_id)
		)
	except Order.DoesNotExist:
		return _json_response(message='Order not found.', success=False, status=404)

	if hasattr(order, 'sale'):
		return _json_response(message='This order has already been converted to a sale.', success=False, status=409)
	if order.status != Order.OrderStatus.CONFIRMED:
		return _json_response(message='Only CONFIRMED orders can be converted to sales.', success=False, status=409)
	if not order.customer:
		return _json_response(message='Order must have a customer before conversion.', success=False, status=400)

	order_items = list(order.items.all())
	if not order_items:
		return _json_response(message='Order must have at least one item before conversion.', success=False, status=400)

	if order.payment_method == Order.PaymentMethod.CREDIT:
		from apps.credits.services import CreditService
		try:
			CreditService.validate_credit_eligibility(order.customer, order.total)
		except ValidationError as error:
			return _validation_response(error.message_dict if hasattr(error, 'message_dict') else {'credit': error.messages})

	try:
		sale = Sale.objects.create(
			sale_number=f'MH-{uuid4().hex[:12].upper()}',
			source_order=order,
			customer=order.customer,
			cashier=request.user,
			status=Sale.SaleStatus.DRAFT,
			payment_method=order.payment_method,
			payment_status=Sale.PaymentStatus.PENDING,
			subtotal=order.subtotal,
			discount=order.discount,
			total=order.total,
			notes=order.notes,
		)
		for order_item in order_items:
			SaleItem.objects.create(
				sale=sale,
				product=order_item.product,
				quantity=order_item.quantity,
				unit_price=order_item.unit_price,
				discount=Decimal('0.00'),
				product_name_snapshot=order_item.product_name_snapshot,
				sku_snapshot=order_item.sku_snapshot,
			)
		sale.complete_sale()
		order.status = Order.OrderStatus.COMPLETED
		order.save(update_fields=['status', 'updated_at'])
		_notify_order_recipients(
			order,
			title='Order completed',
			message=f'{order.order_number} was completed and processed as a sale.',
			recipients=[order.customer] if order.customer_id else [],
		)
	except IntegrityError:
		return _json_response(message='This order has already been converted to a sale.', success=False, status=409)
	except ValidationError as error:
		transaction.set_rollback(True)
		return _validation_response(error.message_dict if hasattr(error, 'message_dict') else {'detail': error.messages})

	return _json_response(
		data={'order': _serialize_order(order), 'sale': _serialize_converted_sale(sale)},
		message='Order converted to sale successfully.',
	)


def customer_dashboard_view(request):
	"""
	Customer portal dashboard with live aggregated metrics, credit standing,
	recent orders, and activity stream. Enforces strict customer isolation.
	"""
	if request.method != 'GET':
		return _json_response(message='Only GET is allowed.', success=False, status=405)

	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
	)

	if not _is_authenticated(request.user):
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		login_url = reverse('accounts:login')
		return redirect(f"{login_url}?next={request.path}")

	# RBAC: Customers can access their dashboard. Management can inspect/preview.
	target_customer = request.user
	customer_id_param = request.GET.get('customer_id') or request.GET.get('user_id')

	if request.user.role in MANAGEMENT_ROLES:
		if customer_id_param:
			target_customer = User.objects.filter(id=customer_id_param, role='CUSTOMER').first()
			if not target_customer:
				return _json_response(message='Customer not found.', success=False, status=404)
	else:
		# Non-management user: Customer isolation
		if customer_id_param and str(customer_id_param) != str(request.user.id):
			return _json_response(
				message='Access denied. You cannot view another customer dashboard.',
				success=False,
				status=403,
			)
		if request.user.role != 'CUSTOMER':
			return _json_response(
				message='Access restricted to customer accounts.',
				success=False,
				status=403,
			)

	# 1. Order Metrics
	ACTIVE_STATUSES = [
		Order.OrderStatus.PENDING,
		Order.OrderStatus.CONFIRMED,
		Order.OrderStatus.PROCESSING,
		Order.OrderStatus.READY,
		'OUT_FOR_DELIVERY',
		'READY_FOR_PICKUP',
	]

	orders_qs = Order.objects.filter(customer=target_customer)
	total_orders_count = orders_qs.count()
	active_orders_count = orders_qs.filter(status__in=ACTIVE_STATUSES).count()
	completed_orders_count = orders_qs.filter(status=Order.OrderStatus.COMPLETED).count()

	completed_total = orders_qs.filter(status=Order.OrderStatus.COMPLETED).aggregate(total_spent=Sum('total'))['total_spent']
	total_spent = completed_total if completed_total is not None else Decimal('0.00')

	recent_orders_qs = (
		orders_qs.select_related('created_by')
		.prefetch_related('items')
		.annotate(item_count=Count('items'))
		.order_by('-created_at')[:5]
	)

	recent_orders = []
	for o in recent_orders_qs:
		recent_orders.append({
			'id': o.order_number or f"ORD-{o.id}",
			'order_id': o.id,
			'order_number': o.order_number,
			'date': o.created_at.strftime('%Y-%m-%d') if hasattr(o.created_at, 'strftime') else str(o.created_at),
			'total': float(o.total),
			'items': getattr(o, 'item_count', o.items.count()),
			'status': o.get_status_display() if hasattr(o, 'get_status_display') else o.status,
			'raw_status': o.status,
		})

	# 2. Credit Metrics
	credit_account = getattr(target_customer, 'credit_account', None)
	if credit_account is None:
		try:
			from apps.credits.models import CreditAccount
			credit_account = CreditAccount.objects.filter(customer=target_customer).first()
		except Exception:
			credit_account = None

	if credit_account:
		credit_limit = credit_account.credit_limit
		credit_balance = credit_account.outstanding_balance
		available_credit = credit_account.get_available_credit()
		credit_status = credit_account.get_status_display()
		raw_credit_status = credit_account.status
	else:
		credit_limit = Decimal('0.00')
		credit_balance = Decimal('0.00')
		available_credit = Decimal('0.00')
		credit_status = 'No Credit Account'
		raw_credit_status = 'NONE'

	# 3. Request Metrics
	try:
		from apps.requests.models import Request
		requests_qs = Request.objects.filter(customer=target_customer)
		recent_requests_count = requests_qs.count()
		active_requests_count = requests_qs.filter(
			status__in=[Request.Status.PENDING, Request.Status.REVIEWING, Request.Status.PROCESSING]
		).count()
		recent_requests_list = []
		for r in requests_qs.order_by('-created_at')[:5]:
			recent_requests_list.append({
				'uuid': str(r.uuid),
				'request_number': r.request_number,
				'title': r.title,
				'status': r.get_status_display(),
				'date': r.created_at.strftime('%Y-%m-%d') if hasattr(r.created_at, 'strftime') else str(r.created_at),
			})
	except Exception:
		recent_requests_count = 0
		active_requests_count = 0
		recent_requests_list = []

	# 4. Activity Stream
	activity_stream = []
	try:
		from apps.activity_logs.models import ActivityLog
		logs = ActivityLog.objects.filter(actor=target_customer).order_by('-created_at')[:5]
		for log in logs:
			activity_stream.append({
				'title': log.action_label or log.action_type,
				'text': log.description,
				'date': log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at),
				'timestamp': log.created_at,
			})
	except Exception:
		pass

	try:
		notifs = Notification.objects.filter(recipient=target_customer).order_by('-created_at')[:5]
		for n in notifs:
			activity_stream.append({
				'title': n.title,
				'text': n.message,
				'date': n.created_at.isoformat() if hasattr(n.created_at, 'isoformat') else str(n.created_at),
				'timestamp': n.created_at,
			})
	except Exception:
		pass

	activity_stream.sort(key=lambda x: str(x.get('timestamp') or ''), reverse=True)
	recent_activity = [
		{'title': item['title'], 'text': item['text'], 'date': item['date']}
		for item in activity_stream[:5]
	]

	# 5. Format payload
	dashboard_data = {
		'customer': {
			'id': target_customer.id,
			'name': target_customer.get_full_name() or target_customer.username,
			'email': target_customer.email,
			'member_since': target_customer.created_at.strftime('%Y-%m-%d') if hasattr(target_customer.created_at, 'strftime') else '',
		},
		'summary': {
			'total_orders': total_orders_count,
			'active_orders': active_orders_count,
			'completed_orders': completed_orders_count,
			'total_spent': float(total_spent),
			'credit_balance': float(credit_balance),
			'available_credit': float(available_credit),
			'credit_limit': float(credit_limit),
			'credit_status': credit_status,
			'raw_credit_status': raw_credit_status,
			'recent_requests': recent_requests_count,
			'active_requests': active_requests_count,
		},
		'recent_orders': recent_orders,
		'recent_requests': recent_requests_list,
		'recent_activity': recent_activity,
	}

	if wants_json:
		return _json_response(data=dashboard_data, message='Customer dashboard metrics retrieved successfully.')

	context = {
		'customer': target_customer,
		'dashboard_data': dashboard_data,
		'dashboard_json': json.dumps(dashboard_data),
		'summary': dashboard_data['summary'],
		'recent_orders': recent_orders,
		'recent_activity': recent_activity,
	}
	return render(request, 'customer/dashboard.html', context)


# ============================================================================
# CUSTOMER CART & CHECKOUT VIEWS
# ============================================================================

def customer_cart_view(request):
	"""
	GET/POST /customer/cart/

	Customer shopping cart view and session item management.
	GET: Dual format - renders customer/cart.html or returns JSON (?format=json).
	POST: Clears or mutates cart based on payload.
	Security: Requires authentication.
	"""
	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
		or 'application/json' in getattr(request, 'content_type', '')
	)

	if not _is_authenticated(request.user):
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		login_url = reverse('accounts:login')
		return redirect(f"{login_url}?next={request.path}")

	cart = CustomerCart(request)

	if request.method == 'POST':
		payload, _ = _parse_json_body(request)
		data = payload if payload is not None else request.POST.dict()
		action = str(data.get('action') or '').strip().lower()

		if action == 'clear' or data.get('clear') in (True, 'true', '1'):
			cart.clear()
			cart_data = cart.get_cart_data()
			if wants_json:
				return _json_response(data=cart_data, message='Cart cleared successfully.')
			return redirect(reverse('customer_orders:cart'))

		product_id = data.get('product_id')
		if product_id:
			try:
				product = Product.objects.select_related('inventory_item').get(pk=int(product_id), is_active=True)
			except (Product.DoesNotExist, ValueError, TypeError):
				return _json_response(message='Product not found or inactive.', success=False, status=404)

			try:
				quantity = int(data.get('quantity', 1))
			except (ValueError, TypeError):
				return _validation_response({'quantity': 'Quantity must be an integer.'})

			if action == 'remove':
				cart.remove(product.id)
				success, msg = True, 'Item removed from cart.'
			elif action in ('update', 'set'):
				success, msg, _ = cart.set_quantity(product, quantity)
			else:
				success, msg, _ = cart.add(product, quantity)

			if not success:
				return _validation_response({'quantity': msg})

			cart_data = cart.get_cart_data()
			if wants_json:
				return _json_response(data=cart_data, message=msg)
			return redirect(reverse('customer_orders:cart'))

		return _json_response(message='Invalid cart operation.', success=False, status=400)

	if request.method != 'GET':
		return _json_response(message='Only GET and POST are allowed.', success=False, status=405)

	cart_data = cart.get_cart_data()
	if wants_json:
		return _json_response(data=cart_data, message='Cart retrieved successfully.')

	context = {
		'cart': cart_data,
		'cart_json': json.dumps(cart_data),
		'items': cart_data['items'],
		'item_count': cart_data['item_count'],
		'subtotal': cart_data['subtotal'],
		'total': cart_data['total'],
	}
	return render(request, 'customer/cart.html', context)


def customer_cart_items_view(request):
	"""
	GET/POST/DELETE /customer/cart/items/

	Cart items endpoint.
	GET: returns JSON list of items and subtotal.
	POST: add, update, or remove line item with strict inventory boundary validation.
	DELETE: clear cart or remove specified product_id.
	"""
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)

	cart = CustomerCart(request)

	if request.method == 'GET':
		cart_data = cart.get_cart_data()
		return _json_response(data=cart_data, message='Cart items retrieved successfully.')

	if request.method == 'DELETE':
		payload, _ = _parse_json_body(request)
		data = payload or {}
		product_id = data.get('product_id') or request.GET.get('product_id')
		if product_id:
			cart.remove(product_id)
			return _json_response(data=cart.get_cart_data(), message='Item removed from cart.')
		cart.clear()
		return _json_response(data=cart.get_cart_data(), message='Cart cleared successfully.')

	if request.method == 'POST':
		payload, body_errors = _parse_json_body(request)
		data = payload if payload is not None else request.POST.dict()

		product_id = data.get('product_id')
		if not product_id:
			return _validation_response({'product_id': 'Product ID is required.'})

		try:
			product = Product.objects.select_related('inventory_item').get(pk=int(product_id), is_active=True)
		except (Product.DoesNotExist, ValueError, TypeError):
			return _json_response(message='Product not found or inactive.', success=False, status=404)

		action = str(data.get('action') or 'add').strip().lower()
		if action == 'remove':
			cart.remove(product.id)
			return _json_response(data=cart.get_cart_data(), message='Item removed from cart.')

		try:
			quantity = int(data.get('quantity', 1))
		except (ValueError, TypeError):
			return _validation_response({'quantity': 'Quantity must be an integer.'})

		if action in ('update', 'set'):
			success, msg, _ = cart.set_quantity(product, quantity)
		else:
			success, msg, _ = cart.add(product, quantity)

		if not success:
			return _validation_response({'quantity': msg})

		return _json_response(data=cart.get_cart_data(), message=msg)

	return _json_response(message='Method not allowed.', success=False, status=405)


def customer_cart_item_detail_view(request, product_id):
	"""
	POST/DELETE/PATCH /customer/cart/items/<int:product_id>/
	"""
	if not _is_authenticated(request.user):
		return _json_response(message='Authentication required.', success=False, status=401)

	cart = CustomerCart(request)

	if request.method in ('DELETE',):
		cart.remove(product_id)
		return _json_response(data=cart.get_cart_data(), message='Item removed from cart.')

	if request.method in ('POST', 'PATCH', 'PUT'):
		payload, _ = _parse_json_body(request)
		data = payload if payload is not None else request.POST.dict()

		action = str(data.get('action') or 'update').strip().lower()
		if action == 'remove':
			cart.remove(product_id)
			return _json_response(data=cart.get_cart_data(), message='Item removed from cart.')

		try:
			product = Product.objects.select_related('inventory_item').get(pk=int(product_id), is_active=True)
		except (Product.DoesNotExist, ValueError, TypeError):
			return _json_response(message='Product not found or inactive.', success=False, status=404)

		try:
			quantity = int(data.get('quantity', 1))
		except (ValueError, TypeError):
			return _validation_response({'quantity': 'Quantity must be an integer.'})

		if action == 'add':
			success, msg, _ = cart.add(product, quantity)
		else:
			success, msg, _ = cart.set_quantity(product, quantity)

		if not success:
			return _validation_response({'quantity': msg})

		return _json_response(data=cart.get_cart_data(), message=msg)

	if request.method == 'GET':
		qty = cart.get_quantity(product_id)
		return _json_response(data={'product_id': product_id, 'quantity': qty}, message='Cart item retrieved.')

	return _json_response(message='Method not allowed.', success=False, status=405)


def customer_checkout_view(request):
	"""
	GET/POST /customer/checkout/

	Customer checkout review & order placement.
	GET: Renders order review with items breakdown, subtotal, tax/shipping, total, and customer credit status.
	POST: Validates items and stock bounds, enforces credit eligibility if CREDIT method chosen,
	      creates Order (status=PENDING) and OrderItems, emits notifications, and records activity log.
	Security: Strictly attributes order to customer=request.user; requires authentication.
	"""
	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
		or 'application/json' in getattr(request, 'content_type', '')
	)

	if not _is_authenticated(request.user):
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		login_url = reverse('accounts:login')
		return redirect(f"{login_url}?next={request.path}")

	# RBAC: Only customers can submit orders; management can preview review
	if request.user.role not in ('CUSTOMER', *MANAGEMENT_ROLES):
		return _json_response(message='Customer access required.', success=False, status=403)

	cart = CustomerCart(request)

	if request.method == 'GET':
		cart_data = cart.get_cart_data()
		total_decimal = Decimal(cart_data['total'])
		delivery_zones = list(DeliveryZone.objects.filter(is_active=True).order_by('name').values('id', 'name', 'fee', 'estimated_delivery_time'))

		credit_account = getattr(request.user, 'credit_account', None)
		if credit_account is None:
			try:
				from apps.credits.models import CreditAccount
				credit_account = CreditAccount.objects.filter(customer=request.user).first()
			except Exception:
				credit_account = None

		if credit_account:
			available_credit = credit_account.get_available_credit()
			can_use = credit_account.can_use_credit(total_decimal) if total_decimal > 0 else True
			credit_info = {
				'has_account': True,
				'status': credit_account.get_status_display(),
				'raw_status': credit_account.status,
				'credit_limit': str(credit_account.credit_limit),
				'outstanding_balance': str(credit_account.outstanding_balance),
				'available_credit': str(available_credit),
				'can_use_credit': can_use,
			}
		else:
			credit_info = {
				'has_account': False,
				'status': 'No Credit Account',
				'raw_status': 'NONE',
				'credit_limit': '0.00',
				'outstanding_balance': '0.00',
				'available_credit': '0.00',
				'can_use_credit': False,
			}

		allow_cod = cart_data.get('allow_cod', True)
		review_data = {
			'items': cart_data['items'],
			'item_count': cart_data['item_count'],
			'subtotal': cart_data['subtotal'],
			'tax': cart_data['tax'],
			'delivery': cart_data['delivery'],
			'shipping': cart_data['shipping'],
			'total': cart_data['total'],
			'delivery_zones': [{'id': zone['id'], 'name': zone['name'], 'fee': str(zone['fee']), 'estimated_delivery_time': zone['estimated_delivery_time']} for zone in delivery_zones],
			'allow_cod': allow_cod,
			'credit': credit_info,
			'customer': {
				'id': request.user.id,
				'name': request.user.get_full_name() or request.user.username,
				'email': request.user.email,
				'phone': getattr(request.user, 'phone_number', '') or '',
			},
		}

		if wants_json:
			return _json_response(data=review_data, message='Checkout review retrieved successfully.')

		context = {
			'checkout': review_data,
			'checkout_json': json.dumps(review_data),
			'items': review_data['items'],
			'subtotal': review_data['subtotal'],
			'tax': review_data['tax'],
			'delivery': review_data['delivery'],
			'total': review_data['total'],
			'delivery_zones': review_data['delivery_zones'],
			'allow_cod': allow_cod,
			'credit': credit_info,
			'customer': request.user,
		}
		return render(request, 'customer/checkout.html', context)

	if request.method == 'POST':
		if request.user.role != 'CUSTOMER':
			return _json_response(message='Only customer accounts can place orders.', success=False, status=403)

		payload, _ = _parse_json_body(request)
		data = payload if payload is not None else request.POST.dict()

		# Reject Moniepoint or QR payment rails on customer storefront (exclusive to cashier POS)
		raw_payment_method = str(data.get('payment_method') or data.get('paymentMethod') or '').strip().lower()
		if raw_payment_method in ['moniepoint', 'qr', 'bank_transfer', 'transfer']:
			return _json_response(
				message='Dynamic QR and direct Moniepoint bank transfer payments are only available at in-store POS terminals. Please select Paystack online or Pay on Delivery.',
				errors={'payment_method': 'Dynamic QR and direct Moniepoint bank transfer payments are not available for customer online checkout. Please pay online via Paystack or select Pay on Delivery.'},
				success=False,
				status=400,
			)

		# Normalize payment method: paystack (default online), cod (pay on delivery), credit (store credit line)
		if raw_payment_method in ['cod', 'cash', 'pay_on_delivery']:
			normalized_method = 'cod'
			order_payment_method = Order.PaymentMethod.CASH
		elif raw_payment_method in ['paystack', 'card', 'online', 'card_online'] or not raw_payment_method:
			normalized_method = 'paystack'
			order_payment_method = Order.PaymentMethod.CARD
		elif raw_payment_method in ['credit']:
			normalized_method = 'credit'
			order_payment_method = Order.PaymentMethod.CREDIT
		else:
			return _validation_response({'payment_method': f"Invalid or unsupported payment method '{raw_payment_method}'."})

		# Resolve items from request payload or fallback to customer session cart
		item_payloads = data.get('items')
		if not isinstance(item_payloads, list) or not item_payloads:
			cart_data = cart.get_cart_data()
			if not cart_data['items']:
				return _validation_response({'items': 'Cannot place order with an empty cart.'})
			item_payloads = [{'product_id': it['id'], 'quantity': it['quantity']} for it in cart_data['items']]

		delivery_address = str(data.get('delivery_address') or data.get('address') or '').strip()
		delivery_zone_id = data.get('delivery_zone_id') or data.get('delivery_zone')
		customer_phone = str(data.get('customer_phone') or data.get('phone') or '').strip()
		delivery_type = str(data.get('delivery_type') or '').strip()
		notes = str(data.get('notes') or '').strip()
		if delivery_type and delivery_type not in notes:
			notes = f"Delivery Method: {delivery_type} | {notes}".strip(' |')

		errors = {}
		prepared_items = []
		subtotal = Decimal('0.00')
		seen_products = set()

		for idx, it in enumerate(item_payloads):
			prefix = f'items[{idx}]'
			if not isinstance(it, dict):
				errors[prefix] = 'Item must be a JSON object.'
				continue
			pid = it.get('product_id') or it.get('id')
			try:
				product = Product.objects.select_related('inventory_item').get(pk=int(pid))
			except (Product.DoesNotExist, ValueError, TypeError):
				errors[f'{prefix}.product_id'] = 'Product not found.'
				continue

			if not product.is_active:
				errors[f'{prefix}.product_id'] = f"Product '{product.name}' is inactive."
				continue

			if product.id in seen_products:
				errors[f'{prefix}.product_id'] = 'Duplicate products are not allowed.'
				continue
			seen_products.add(product.id)

			try:
				qty = _parse_positive_integer(it.get('quantity'))
			except (ValueError, TypeError):
				errors[f'{prefix}.quantity'] = 'Quantity must be a positive integer.'
				continue

			available_stock = (
				getattr(product, 'inventory_item', None).quantity
				if hasattr(product, 'inventory_item') and product.inventory_item
				else 0
			)
			if qty > available_stock:
				errors[f'{prefix}.quantity'] = (
					f"Insufficient stock for '{product.name}'. Available: {available_stock}, requested: {qty}."
				)
				continue

			prepared_items.append((product, qty))
			subtotal += product.selling_price * qty

		if errors:
			return _validation_response(errors)

		delivery_zone = None
		delivery_fee = Decimal('0.00')
		if delivery_type and delivery_type.lower() != 'pickup':
			if not delivery_zone_id:
				return _validation_response({'delivery_zone_id': 'Choose a delivery area.'})
			delivery_zone = DeliveryZone.objects.filter(pk=delivery_zone_id, is_active=True).first()
			if not delivery_zone:
				return _validation_response({'delivery_zone_id': 'That delivery area is unavailable. Refresh checkout and select an active area.'})
			delivery_fee = delivery_zone.fee
		checkout_total = subtotal + delivery_fee

		# Conditional Pay on Delivery check across all cart products
		allow_cod = all(getattr(product, 'allow_pay_on_delivery', True) for product, _ in prepared_items) if prepared_items else True
		if normalized_method == 'cod' and not allow_cod:
			return _json_response(
				message='One or more items in your cart are not eligible for Pay on Delivery. Please pay online via Paystack.',
				errors={'payment_method': 'Requires upfront online payment'},
				success=False,
				status=400,
			)

		# Credit checkout validation rule
		credit_account = None
		if order_payment_method == Order.PaymentMethod.CREDIT:
			from apps.credits.services import CreditService
			try:
				credit_account = CreditService.validate_credit_eligibility(request.user, checkout_total)
			except ValidationError as credit_error:
				credit_errors = credit_error.message_dict if hasattr(credit_error, 'message_dict') else {'credit': credit_error.messages}
				return _validation_response(credit_errors)

			available_credit = credit_account.get_available_credit()
			if checkout_total > available_credit:
				return _validation_response({
					'credit': f'Credit limit exceeded: Available credit is ₦{available_credit:.2f}, but cart total is ₦{subtotal:.2f}.'
				})

		try:
			with transaction.atomic():
				initial_payment_status = (
					Order.PaymentStatus.PAID_BY_CREDIT
					if order_payment_method == Order.PaymentMethod.CREDIT
					else Order.PaymentStatus.PENDING
				)
				order = Order.objects.create(
					order_number=_generate_order_number(),
					customer=request.user,
					status=Order.OrderStatus.PENDING,
					payment_method=order_payment_method,
					payment_status=initial_payment_status,
					discount=Decimal('0.00'),
					subtotal=subtotal,
					delivery_fee=delivery_fee,
					delivery_zone=delivery_zone,
					total=checkout_total,
					delivery_address=delivery_address,
					customer_phone=customer_phone,
					notes=notes,
				)
				for product, qty in prepared_items:
					item = OrderItem.create_from_product(product=product, order=order, quantity=qty)
					item.save()

				# If paid by credit, atomically update customer credit ledger
				if order_payment_method == Order.PaymentMethod.CREDIT and credit_account is not None:
					from apps.credits.models import CreditAccount, CreditTransaction
					account = CreditAccount.objects.select_for_update().get(pk=credit_account.pk)
					if checkout_total > account.get_available_credit():
						raise ValidationError({
							'credit': f'Credit limit exceeded: Available credit is ₦{account.get_available_credit():.2f}, but order total is ₦{subtotal:.2f}.'
						})
					previous_balance = account.outstanding_balance
					new_balance = previous_balance + checkout_total
					account.outstanding_balance = new_balance
					if account.status == account.Status.APPROVED:
						account.status = account.Status.ACTIVE
					account.save(update_fields=['outstanding_balance', 'status', 'updated_at'])

					CreditTransaction.objects.create(
						credit_account=account,
						transaction_type=CreditTransaction.TransactionType.CREDIT_PURCHASE,
						amount=checkout_total,
						previous_balance=previous_balance,
						new_balance=new_balance,
						reference=f'CRD-ORD-{order.order_number}',
						notes=f'Credit purchase for Customer Order {order.order_number}',
						created_by=request.user,
					)

				# Clear cart upon successful order creation
				cart.clear()
		except ValidationError as val_err:
			return _validation_response(val_err.message_dict if hasattr(val_err, 'message_dict') else {'detail': val_err.messages})

		# Notifications
		try:
			from apps.notifications.services import NotificationService
			NotificationService.create_notification(
				recipient=request.user,
				notification_type=Notification.NotificationType.ORDER,
				title='Order Placed Successfully',
				message=f'Your order {order.order_number} for ₦{order.total} has been placed and is pending review.',
				priority=Notification.Priority.NORMAL,
				related_object=order,
				action_url=f'/customer/orders/{order.id}/',
				actor=request.user,
			)

			staff_recipients = User.objects.filter(
				role__in=['OWNER', 'MANAGER', 'CASHIER'],
				is_active=True,
			)
			for staff in staff_recipients:
				NotificationService.create_notification(
					recipient=staff,
					notification_type=Notification.NotificationType.ORDER,
					title='New Customer Order Placed',
					message=f'New order {order.order_number} placed by {request.user.get_full_name() or request.user.email} (Total: ₦{order.total}).',
					priority=Notification.Priority.HIGH,
					related_object=order,
					action_url=f'/orders/{order.id}/',
					actor=request.user,
				)
		except Exception:
			pass

		# Audit log via log_activity
		try:
			from apps.activity_logs.models import ActivityLog
			from apps.activity_logs.services import log_activity
			log_activity(
				actor=request.user,
				action_type=ActivityLog.ActionType.CREATED,
				action_label='Order Placed',
				description=f'Customer placed order {order.order_number} for ₦{order.total} via {order.get_payment_method_display()}.',
				related_object=order,
				metadata={
					'order_number': order.order_number,
					'total': str(order.total),
					'item_count': len(prepared_items),
					'payment_method': order.payment_method,
				},
				request=request,
			)
		except Exception:
			pass

		payment_intent = None
		if order_payment_method == Order.PaymentMethod.CARD:
			try:
				from apps.payments.paystack_service import PaystackService
				callback_url = request.build_absolute_uri(reverse('customer_orders:order_detail', args=[order.id]))
				pay_email = request.user.email or f"customer_{request.user.id}@madamhy.com"
				init_res = PaystackService.initialize_transaction(
					target=order,
					email=pay_email,
					amount=order.total,
					callback_url=callback_url,
				)
				payment_intent = {
					'method': 'CARD',
					'provider': 'paystack',
					'status': 'success' if init_res.get('success', True) else 'failed',
					'success': init_res.get('success', True),
					'authorization_url': init_res.get('authorization_url'),
					'access_code': init_res.get('access_code'),
					'reference': init_res.get('reference'),
				}
			except Exception as pay_err:
				payment_intent = {'method': 'CARD', 'provider': 'paystack', 'status': 'failed', 'success': False, 'error': str(pay_err)}

		elif order_payment_method == Order.PaymentMethod.CREDIT:
			payment_intent = {
				'method': 'CREDIT',
				'status': 'PAID_BY_CREDIT',
				'payment_status': 'PAID_BY_CREDIT',
				'success': True,
				'message': 'Order successfully charged to verified credit facility.',
			}
		else:
			payment_intent = {
				'method': 'CASH',
				'provider': 'cod',
				'status': 'success',
				'success': True,
				'message': 'Payment will be settled with cash or card upon doorstep delivery.',
			}

		order = Order.objects.select_related('customer').prefetch_related('items').get(pk=order.pk)
		if wants_json:
			return _json_response(
				data={
					'status': 'success',
					'order': _serialize_order(order),
					'payment': payment_intent,
					'authorization_url': payment_intent.get('authorization_url') if payment_intent else None,
					'order_reference': order.order_number,
				},
				message='Order placed successfully.',
				status=201,
			)

		return redirect(reverse('customer_orders:order_detail', args=[order.id]))

	return _json_response(message='Only GET and POST are allowed.', success=False, status=405)


def customer_order_success_view(request, order_id=None):
	"""
	Renders customer/order_success.html with confirmed order summary,
	payment breakdown, and printable receipt.
	Supports lookup by order_id or ?ref=<order_number>.
	"""
	if not _is_authenticated(request.user):
		return redirect(f"{reverse('accounts:login')}?next={request.path}")
	if getattr(request.user, 'role', None) != 'CUSTOMER':
		return redirect('/dashboard/')

	ref = request.GET.get('ref') or request.GET.get('order_number')
	try:
		if order_id:
			order = Order.objects.select_related('customer').prefetch_related('items').get(pk=order_id, customer=request.user)
		elif ref:
			order = Order.objects.select_related('customer').prefetch_related('items').get(order_number=ref, customer=request.user)
		else:
			from django.http import Http404
			raise Http404('Order reference required.')
	except Order.DoesNotExist:
		if (order_id and Order.objects.filter(pk=order_id).exists()) or (ref and Order.objects.filter(order_number=ref).exists()):
			return _json_response(message='You do not have permission to view this order.', success=False, status=403)
		from django.http import Http404
		raise Http404('Order not found.')

	serialized_order = _serialize_order(order)
	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
	)
	if wants_json:
		return _json_response(data={'order': serialized_order}, message='Order confirmation retrieved.')

	return render(request, 'customer/order_success.html', {
		'order': order,
		'order_data': serialized_order,
		'order_json': json.dumps(serialized_order),
	})


def customer_credit_view(request):
	"""Render customer credit account view (customer/credit.html)."""
	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
	)
	if not _is_authenticated(request.user):
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		return redirect(f"{reverse('accounts:login')}?next=/customer/credit/")
	if getattr(request.user, 'role', None) != 'CUSTOMER':
		if wants_json:
			return _json_response(message='Access denied.', success=False, status=403)
		return redirect('/dashboard/')

	from apps.credits.models import CreditAccount
	credit_account = CreditAccount.objects.filter(customer=request.user).first()
	if wants_json:
		return _json_response(data={
			'credit_limit': float(credit_account.credit_limit) if credit_account else 0.0,
			'outstanding_balance': float(credit_account.outstanding_balance) if credit_account else 0.0,
			'status': credit_account.status if credit_account else 'INACTIVE',
		}, message='Credit account retrieved.')
	context = {
		'credit_account': credit_account,
		'credit_transactions': credit_account.transactions.all()[:20] if credit_account else [],
	}
	return render(request, 'customer/credit.html', context)


def customer_activity_view(request):
	"""Render customer activity timeline view (customer/activity.html)."""
	wants_json = (
		request.GET.get('format') == 'json'
		or 'application/json' in request.headers.get('Accept', '')
	)
	if not _is_authenticated(request.user):
		if wants_json:
			return _json_response(message='Authentication required.', success=False, status=401)
		return redirect(f"{reverse('accounts:login')}?next=/customer/activity/")
	if getattr(request.user, 'role', None) != 'CUSTOMER':
		if wants_json:
			return _json_response(message='Access denied.', success=False, status=403)
		return redirect('/dashboard/')

	from apps.activity_logs.models import ActivityLog
	recent_activities = ActivityLog.objects.filter(actor=request.user).order_by('-created_at')[:20]
	if wants_json:
		return _json_response(data={
			'activities': [
				{
					'action_type': a.action_type,
					'action_label': a.action_label,
					'description': a.description,
					'timestamp': a.created_at.isoformat(),
				}
				for a in recent_activities
			]
		}, message='Activity history retrieved.')
	context = {
		'recent_activities': recent_activities,
	}
	return render(request, 'customer/activity.html', context)
