import json
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.sales.models import Sale

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity

from .models import Payment
from .qr_service import QRCodeService
from .reconciliation import ReconciliationService
from .refund_service import PaymentRefundService, RefundChannel
from .resolution import PaymentResolutionService, ResolutionStrategy
from .services import PaymentService
from .verification import PaymentVerificationService, PaymentVerificationStatus, verify_payment_transaction

User = get_user_model()
MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
    payload = {'success': success, 'message': message}
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    response = JsonResponse(payload, status=status)
    if data is not None and isinstance(data, dict):
        response.context = {**payload, **data}
    elif data is not None:
        response.context = payload
    return response


def _is_authenticated(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def _can_view_payments(user):
    return _is_authenticated(user) and getattr(user, 'role', None) in (*MANAGEMENT_ROLES, 'CUSTOMER')


def _can_manage_payments(user):
    return _is_authenticated(user) and getattr(user, 'role', None) in MANAGEMENT_ROLES


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


def _serialize_user(user):
    if user is None:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'role': user.role,
    }


def _serialize_payment(payment):
    order_ref = '-'
    if payment.order:
        order_ref = getattr(payment.order, 'order_number', '-')
    elif payment.sale:
        order_ref = getattr(payment.sale, 'sale_number', '-')

    cust_name = 'Walk-in Customer'
    if payment.customer:
        cust_name = payment.customer.get_full_name() or payment.customer.username

    method_display = payment.get_payment_method_display() if hasattr(payment, 'get_payment_method_display') else str(payment.payment_method)
    status_display = payment.get_payment_status_display() if hasattr(payment, 'get_payment_status_display') else str(payment.payment_status)

    return {
        'id': payment.id,
        'payment_reference': payment.payment_reference,
        'reference': payment.payment_reference,
        'sale_id': payment.sale_id,
        'order_id': payment.order_id,
        'order_number': order_ref,
        'orderNumber': order_ref,
        'customer': _serialize_user(payment.customer),
        'customer_name': cust_name,
        'customerName': cust_name,
        'cashier': _serialize_user(payment.cashier),
        'amount': str(payment.amount),
        'amount_num': float(payment.amount) if payment.amount else 0.0,
        'payment_method': payment.payment_method,
        'method': method_display,
        'payment_status': payment.payment_status,
        'status': status_display,
        'transaction_reference': payment.transaction_reference,
        'transaction_metadata': payment.transaction_metadata,
        'notes': payment.notes,
        'date': payment.created_at.isoformat(),
        'created_at': payment.created_at.isoformat(),
        'updated_at': payment.updated_at.isoformat(),
    }


def _parse_json_body(request):
    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, {'body': 'Request body must be valid JSON.'}
    if not isinstance(payload, dict):
        return None, {'body': 'Request body must be a JSON object.'}
    return payload, None


def _parse_money_value(value, field_name):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, {field_name: 'Must be a valid monetary amount.'}
    if not amount.is_finite() or amount <= 0:
        return None, {field_name: 'Amount must be greater than zero.'}
    if amount.as_tuple().exponent < -2:
        return None, {field_name: 'Amount cannot have more than two decimal places.'}
    return amount, None


def _generate_payment_reference():
    return f'PMT-{uuid.uuid4().hex[:12].upper()}'


def payment_list(request):
    if request.method == 'GET' and not _wants_json(request):
        if not _is_authenticated(request.user):
            return redirect(f"{reverse('accounts:login')}?next=/payments/")
        if not _can_view_payments(request.user):
            return redirect(f"{reverse('accounts:login')}?next=/payments/")
        view_type = (request.GET.get('view') or '').lower()
        active_tab = 'methods' if view_type == 'methods' or request.GET.get('payment_method') else 'records'

        payments_qs = Payment.objects.select_related('customer', 'cashier', 'sale', 'order').order_by('-created_at')
        if request.user.role == 'CUSTOMER':
            payments_qs = payments_qs.filter(customer=request.user)

        total_count = payments_qs.count()
        successful_count = payments_qs.filter(payment_status=Payment.PaymentStatus.COMPLETED).count()
        pending_count = payments_qs.filter(payment_status=Payment.PaymentStatus.PENDING).count()
        total_amount = sum((p.amount for p in payments_qs.filter(payment_status=Payment.PaymentStatus.COMPLETED)), Decimal('0.00'))
        serialized_payments = [_serialize_payment(p) for p in payments_qs[:100]]

        return render(request, 'payments/payments.html', {
            'active_module': 'payments',
            'active_tab': active_tab,
            'payments': payments_qs[:100],
            'payments_serialized': serialized_payments,
            'payments_json': json.dumps(serialized_payments),
            'total_count': total_count,
            'successful_count': successful_count,
            'pending_count': pending_count,
            'total_amount': total_amount,
        })

    if request.method == 'POST':
        return payment_create(request)
    if request.method != 'GET':
        return _json_response(message='Only GET and POST are allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if not _can_view_payments(request.user):
        return _json_response(message='You do not have permission to view payments.', success=False, status=403)

    payments = Payment.objects.select_related('customer', 'cashier', 'sale', 'order')
    if request.user.role == 'CUSTOMER':
        payments = payments.filter(customer=request.user)

    search = (request.GET.get('search') or '').strip()
    if search:
        payments = payments.filter(
            Q(payment_reference__icontains=search)
            | Q(transaction_reference__icontains=search)
            | Q(notes__icontains=search)
        )

    page = 1
    page_size = 10
    try:
        page = max(1, int(request.GET.get('page', 1)))
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
    except (TypeError, ValueError):
        page = 1
        page_size = 10

    total_count = payments.count()
    start = (page - 1) * page_size
    items = list(payments[start:start + page_size])
    return _json_response(
        data={
            'payments': [_serialize_payment(payment) for payment in items],
            'pagination': {
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size,
            },
        },
        message='Payments retrieved successfully.',
    )


def payment_create(request):
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if not _can_manage_payments(request.user):
        return _json_response(message='You do not have permission to create payments.', success=False, status=403)

    payload, errors = _parse_json_body(request)
    if errors:
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    sale_id = payload.get('sale_id')
    order_id = payload.get('order_id')
    if sale_id is not None and order_id is not None:
        return _json_response(message='Validation failed.', success=False, status=400, errors={'transaction': 'A payment must be linked to either a sale or an order, not both.'})
    if sale_id is None and order_id is None:
        return _json_response(message='Validation failed.', success=False, status=400, errors={'transaction': 'A sale_id or order_id is required.'})

    sale = None
    order = None
    if sale_id is not None:
        try:
            sale = Sale.objects.select_related('customer').get(pk=sale_id)
        except Sale.DoesNotExist:
            return _json_response(message='Validation failed.', success=False, status=400, errors={'sale_id': 'Sale not found.'})
    if order_id is not None:
        try:
            order = Order.objects.select_related('customer').get(pk=order_id)
        except Order.DoesNotExist:
            return _json_response(message='Validation failed.', success=False, status=400, errors={'order_id': 'Order not found.'})

    customer_id = payload.get('customer_id')
    customer = None
    if customer_id is not None:
        try:
            customer = User.objects.get(pk=customer_id)
        except (User.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Validation failed.', success=False, status=400, errors={'customer_id': 'Customer not found.'})
    else:
        customer = sale.customer if sale else order.customer

    cashier_id = payload.get('cashier_id', request.user.id)
    try:
        cashier = User.objects.get(pk=cashier_id)
    except (User.DoesNotExist, TypeError, ValueError):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'cashier_id': 'Cashier not found.'})

    metadata = payload.get('transaction_metadata') or {}
    if not isinstance(metadata, dict):
        return _json_response(message='Validation failed.', success=False, status=400, errors={'transaction_metadata': 'transaction_metadata must be a JSON object.'})

    idempotency_key = (request.headers.get('X-Idempotency-Key') or '').strip()
    if len(idempotency_key) > 120:
        return _json_response(message='Validation failed.', success=False, status=400, errors={'idempotency_key': 'Idempotency key cannot exceed 120 characters.'})

    try:
        payment = PaymentService.create_payment(
            payment_reference=_generate_payment_reference(),
            idempotency_key=idempotency_key,
            sale=sale,
            order=order,
            customer=customer,
            cashier=cashier,
            amount=payload.get('amount'),
            payment_method=payload.get('payment_method'),
            payment_status=payload.get('payment_status', Payment.PaymentStatus.PENDING),
            transaction_reference=(payload.get('transaction_reference') or '').strip(),
            transaction_metadata=metadata,
            notes=(payload.get('notes') or '').strip(),
        )
    except ValidationError as exc:
        return _json_response(message='Validation failed.', success=False, status=400, errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages})

    payment_data = _serialize_payment(payment)
    return _json_response(
        data=payment_data,
        message='Payment created successfully.',
        success=True,
        status=201,
    )


def payment_detail(request, payment_id):
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        if not _wants_json(request):
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        return _json_response(message='Authentication required.', success=False, status=401)
    if not _can_view_payments(request.user):
        if not _wants_json(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have permission to view this payment.')
        return _json_response(message='You do not have permission to view this payment.', success=False, status=403)

    queryset = Payment.objects.select_related('customer', 'cashier', 'sale', 'order')
    if request.user.role == 'CUSTOMER':
        queryset = queryset.filter(customer=request.user)

    try:
        payment = queryset.get(pk=payment_id)
    except Payment.DoesNotExist:
        if getattr(request.user, 'role', None) == 'CUSTOMER':
            return _json_response(message='You do not have permission to view this payment.', success=False, status=403)
        if not _wants_json(request):
            from django.http import Http404
            raise Http404('Payment not found.')
        return _json_response(message='Payment not found.', success=False, status=404)

    if request.user.role == 'CUSTOMER' and payment.customer_id != request.user.id:
        return _json_response(message='You do not have permission to view this payment.', success=False, status=403)

    serialized_payment = _serialize_payment(payment)
    if not _wants_json(request):
        return render(request, 'payments/payment_detail.html', {
            'payment': payment,
            'payment_data': serialized_payment,
            'active_module': 'payments',
            'active_tab': 'records',
        })

    return _json_response(data=serialized_payment, message='Payment retrieved successfully.')


def payment_confirm(request, payment_id):
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can confirm payments.', success=False, status=403)

    try:
        payment = PaymentService.confirm_payment(payment_id, request.user)
    except ValidationError as exc:
        if hasattr(exc, 'message_dict') and exc.message_dict.get('payment') == ['Payment not found.']:
            return _json_response(message='Payment not found.', success=False, status=404)
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    return _json_response(
        data=_serialize_payment(payment),
        message='Payment confirmed successfully.',
    )


def payment_verify(request, payment_id):
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can verify payments.', success=False, status=403)

    payment = None
    try:
        payment = Payment.objects.select_related('customer', 'cashier', 'sale', 'order').get(pk=int(str(payment_id)))
    except (Payment.DoesNotExist, TypeError, ValueError):
        pass

    if payment is None:
        payment = Payment.objects.select_related('customer', 'cashier', 'sale', 'order').filter(
            Q(payment_reference=str(payment_id)) | Q(transaction_reference=str(payment_id))
        ).first()

    if payment is None:
        return _json_response(message='Payment not found.', success=False, status=404)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type:
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif request.body and request.body.strip().startswith((b'{', b'[')):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()
    explicit_provider = payload.get('provider') or request.GET.get('provider')
    if explicit_provider:
        provider = explicit_provider.strip().lower()
    else:
        meta = payment.transaction_metadata or {}
        channel = meta.get('channel', '')
        ref = payment.transaction_reference or payment.payment_reference or ''
        if channel == 'PAYSTACK_ONLINE' or ref.startswith('PSTK-'):
            provider = 'paystack'
        elif channel == 'MONIEPOINT_POS' or ref.startswith('MNP-'):
            provider = 'moniepoint'
        else:
            provider = 'mock'
    kwargs = {}
    for key in (
        'expected_amount', 'expected_reference', 'reference', 'secret_key',
        'api_key', 'terminal_serial', 'rrn', 'merchant_reference',
    ):
        val = payload.get(key) if key in payload else request.GET.get(key)
        if val is not None and str(val).strip() != '':
            kwargs[key] = val

    result = PaymentVerificationService.verify_payment_transaction(
        payment=payment,
        provider=provider,
        **kwargs,
    )

    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Verified payment transaction',
        description=f'Payment verification performed for reference {payment.payment_reference}: status {result.status}.',
        related_object=payment,
        metadata={
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'verification_status': result.status,
            'provider': result.provider,
            'discrepancies': result.discrepancies,
        },
    )

    return _json_response(
        data=result.to_dict(),
        message='Payment verification completed.',
        success=True,
        status=200,
    )


def _serialize_reconciliation(result):
    serialized = dict(result)
    for field in (
        'transaction_total', 'completed_amount', 'pending_amount',
        'failed_amount', 'refunded_amount', 'outstanding_amount', 'overpaid_amount',
    ):
        val = serialized[field]
        if val is not None:
            serialized[field] = f"{Decimal(str(val)):.2f}"
    return serialized


def _reconciliation_response(request, transaction_model, transaction_id):
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can access reconciliation.', success=False, status=403)

    try:
        transaction_id = int(transaction_id)
        transaction = transaction_model.objects.get(pk=transaction_id)
    except (transaction_model.DoesNotExist, TypeError, ValueError):
        label = 'Order' if transaction_model is Order else 'Sale'
        return _json_response(message=f'{label} not found.', success=False, status=404)

    try:
        result = ReconciliationService.reconcile(transaction)
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )
    return _json_response(data=_serialize_reconciliation(result), message='Reconciliation retrieved successfully.')


def order_reconciliation(request, order_id):
    return _reconciliation_response(request, Order, order_id)


def sale_reconciliation(request, sale_id):
    return _reconciliation_response(request, Sale, sale_id)


def _management_reconcile_detail(request, transaction_model, transaction_id):
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can access reconciliation.', success=False, status=403)

    is_order = transaction_model is Order
    label = 'Order' if is_order else 'Sale'

    try:
        transaction_pk = int(str(transaction_id))
        transaction = transaction_model.objects.get(pk=transaction_pk)
    except (transaction_model.DoesNotExist, TypeError, ValueError):
        return _json_response(message=f'{label} not found.', success=False, status=404)

    try:
        result = ReconciliationService.reconcile(transaction)
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    identifier = transaction.order_number if is_order else transaction.sale_number
    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label=f'Viewed {label.lower()} reconciliation',
        description=f'Reconciliation report viewed for {label.lower()} {identifier}.',
        related_object=transaction,
        metadata={
            f'{label.lower()}_id': transaction.id,
            f'{label.lower()}_number': identifier,
            'classification': result['classification'],
        },
    )

    return _json_response(
        data=_serialize_reconciliation(result),
        message=f'{label} reconciliation retrieved successfully.',
    )


def reconcile_order(request, order_id):
    return _management_reconcile_detail(request, Order, order_id)


def reconcile_sale(request, sale_id):
    return _management_reconcile_detail(request, Sale, sale_id)


def reconcile_overview(request):
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        if not _wants_json(request):
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        if not _wants_json(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Only owners and managers can access reconciliation.')
        return _json_response(message='Only owners and managers can access reconciliation.', success=False, status=403)

    try:
        limit = min(100, max(1, int(request.GET.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20

    tx_type = (request.GET.get('type') or request.GET.get('transaction_type') or 'ALL').strip().upper()

    sales = []
    orders = []
    if tx_type in ('ALL', 'SALE'):
        sales = list(Sale.objects.all().order_by('-created_at')[:limit])
    if tx_type in ('ALL', 'ORDER'):
        orders = list(Order.objects.all().order_by('-created_at')[:limit])

    combined = sorted(sales + orders, key=lambda item: item.created_at, reverse=True)[:limit]

    serialized_items = []
    for transaction in combined:
        result = ReconciliationService.reconcile(transaction)
        serialized_items.append(_serialize_reconciliation(result))

    classification_counts = {
        'UNPAID': sum(1 for item in serialized_items if item['classification'] == 'UNPAID'),
        'PARTIALLY_PAID': sum(1 for item in serialized_items if item['classification'] == 'PARTIALLY_PAID'),
        'FULLY_PAID': sum(1 for item in serialized_items if item['classification'] == 'FULLY_PAID'),
        'OVERPAID': sum(1 for item in serialized_items if item['classification'] == 'OVERPAID'),
    }
    inconsistency_count = sum(1 for item in serialized_items if len(item.get('inconsistency_findings', [])) > 0)

    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Viewed reconciliation overview',
        description=f'Bulk payment reconciliation overview report viewed ({len(serialized_items)} transactions).',
        metadata={
            'transaction_count': len(serialized_items),
            'summary': classification_counts,
            'inconsistency_count': inconsistency_count,
        },
    )

    data = {
        'summary': {
            'total_transactions': len(serialized_items),
            'classifications': classification_counts,
            'inconsistency_count': inconsistency_count,
        },
        'transactions': serialized_items,
    }

    if not _wants_json(request):
        return render(request, 'payments/reconciliation.html', {
            'active_module': 'payments',
            'active_tab': 'reconcile',
            'summary': data['summary'],
            'transactions': serialized_items,
        })

    return _json_response(data=data, message='Reconciliation overview retrieved successfully.')


def qr_generate(request, target_id=None, target_type=None):
    """
    POST /payments/qr/generate/ or /payments/qr/<target_id>/generate/
    Initializes an in-memory dynamic QR payment code for a Sale or Order.
    Returns SVG/Data-URI image, payment reference, and expiry timestamp.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type:
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif request.body and request.body.strip().startswith((b'{', b'[')):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()

    raw_target_id = target_id or payload.get('target_id') or payload.get('sale_id') or payload.get('order_id')
    raw_type = (target_type or payload.get('target_type') or payload.get('type') or request.GET.get('type') or '').strip().lower()

    target = None
    is_sale = False

    if raw_type in ('sale', 'pos') or payload.get('sale_id'):
        is_sale = True
        try:
            target = Sale.objects.get(pk=int(str(payload.get('sale_id') or raw_target_id)))
        except (Sale.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Sale not found.', success=False, status=404)
    elif raw_type in ('order', 'ord') or payload.get('order_id'):
        is_sale = False
        try:
            target = Order.objects.get(pk=int(str(payload.get('order_id') or raw_target_id)))
        except (Order.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Order not found.', success=False, status=404)
    else:
        if raw_target_id:
            try:
                target = Sale.objects.get(pk=int(str(raw_target_id)))
                is_sale = True
            except (Sale.DoesNotExist, TypeError, ValueError):
                try:
                    target = Order.objects.get(pk=int(str(raw_target_id)))
                    is_sale = False
                except (Order.DoesNotExist, TypeError, ValueError):
                    pass

    if target is None:
        return _json_response(message='A valid Sale or Order target is required.', success=False, status=404)

    user_role = getattr(request.user, 'role', None)

    # RBAC Enforcement:
    # Counter POS sales: only staff/cashiers/managers/owners can generate QR codes
    if is_sale:
        if user_role not in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
            return _json_response(message='Customers cannot generate QR codes for counter sales.', success=False, status=403)
    else:
        # Customer orders: managers/cashiers/owners OR the customer who placed the order
        if user_role in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
            pass
        elif target.customer_id == request.user.id:
            pass
        else:
            return _json_response(message='You can only generate QR codes for your own orders.', success=False, status=403)

    provider = payload.get('provider') or request.GET.get('provider', 'paystack')
    amount = payload.get('amount')
    image_format = payload.get('format') or request.GET.get('format', 'svg')

    try:
        qr_data = QRCodeService.get_or_create_qr_payment(
            target=target,
            provider=provider,
            amount=amount,
            cashier=request.user if is_sale else None,
            customer=target.customer,
            image_format=image_format,
            request=request,
        )
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    label = 'sale' if is_sale else 'order'
    identifier = target.sale_number if is_sale else target.order_number

    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.CREATED,
        action_label='Generated QR payment code',
        description=f'Generated dynamic {provider.upper()} QR payment code for {label} {identifier}.',
        related_object=target,
        metadata={
            'payment_id': qr_data['payment_id'],
            'payment_reference': qr_data['payment_reference'],
            'amount': qr_data['amount'],
            'provider': provider,
            'target_type': label,
            'target_id': target.pk,
        },
    )

    return _json_response(data=qr_data, message='QR payment initialized successfully.')


def qr_status(request, reference):
    """
    GET /payments/qr/<reference>/status/
    Lightweight status check and verification polling for QR payments.
    Allows authenticated staff/customers or unauthenticated polling with valid reference token.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    clean_ref = str(reference).strip()
    payment = Payment.objects.filter(
        Q(payment_reference=clean_ref) | Q(transaction_reference=clean_ref)
    ).first()

    if not payment:
        try:
            payment = Payment.objects.get(pk=int(clean_ref))
        except (Payment.DoesNotExist, TypeError, ValueError):
            pass

    if not payment:
        return _json_response(message='Payment reference not found.', success=False, status=404)

    # Permission check:
    if _is_authenticated(request.user):
        user_role = getattr(request.user, 'role', None)
        if user_role in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
            pass
        elif payment.customer_id == request.user.id:
            pass
        else:
            return _json_response(message='You do not have permission to view this payment status.', success=False, status=403)
    else:
        # Unauthenticated: allow polling if the reference is a non-trivial reference token
        if not (clean_ref.startswith(('QR-', 'TXN-', 'PSTK-')) or len(clean_ref) >= 8):
            return _json_response(message='Authentication required.', success=False, status=401)

    provider = request.GET.get('provider')
    kwargs = {}
    for k in ('secret_key', 'api_key', 'reference'):
        val = request.GET.get(k)
        if val:
            kwargs[k] = val

    status_data = QRCodeService.check_qr_status(reference=clean_ref, provider=provider, **kwargs)

    log_activity(
        actor=request.user if _is_authenticated(request.user) else None,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Polled QR payment status',
        description=f'Polled QR payment status for reference {payment.payment_reference}: {status_data["status"]}.',
        related_object=payment,
        metadata={
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'status': status_data['status'],
            'is_verified': status_data.get('is_verified', False),
            'is_completed': status_data.get('is_completed', False),
        },
    )

    return _json_response(data=status_data, message='QR payment status retrieved.')


def qr_pay_view(request, reference):
    """
    GET /payments/pay/<reference>/ and GET /checkout/pay/<reference>/
    Public customer mobile payment checkout view.
    Renders customer payment page with QR code, bank transfer details, and Paystack checkout.
    """
    clean_ref = str(reference).strip()
    payment = Payment.objects.filter(
        Q(payment_reference=clean_ref) | Q(transaction_reference=clean_ref)
    ).select_related('customer', 'sale', 'order').first()

    if not payment:
        try:
            payment = Payment.objects.select_related('customer', 'sale', 'order').get(pk=int(clean_ref))
        except (Payment.DoesNotExist, TypeError, ValueError):
            payment = None

    wants_json = (
        (request.GET.get('format') or '').lower() == 'json' or
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        ('application/json' in (request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')) and
         'text/html' not in (request.headers.get('Accept', '') or request.META.get('HTTP_ACCEPT', '')))
    )

    if not payment:
        if wants_json:
            return _json_response(message='Payment reference not found.', success=False, status=404)
        return render(request, 'payments/payment_failed.html', {
            'error_message': 'Payment record not found or link has expired.',
            'reference': clean_ref,
        }, status=404)

    if payment.payment_status == Payment.PaymentStatus.COMPLETED:
        if wants_json:
            return _json_response(data=_serialize_payment(payment), message='Payment is already completed.')
        return render(request, 'payments/payment_success.html', {
            'payment': payment,
            'reference': payment.payment_reference,
            'amount': payment.amount,
        })

    meta = payment.transaction_metadata or {}
    details = meta.get('details', {})
    bank_name = details.get('bank_name') or getattr(settings, 'MONIEPOINT_BANK_NAME', 'Moniepoint MFB')
    account_number = details.get('account_number') or getattr(settings, 'MONIEPOINT_COUNTER_ACCOUNT', '') or '-'
    checkout_url = details.get('checkout_url') or meta.get('qr_payload') or f"https://checkout.paystack.com/{payment.transaction_reference or payment.payment_reference}"

    payment_url = request.build_absolute_uri()
    if payment_url.startswith('http://'):
        payment_url = 'https://' + payment_url[7:]

    qr_code_data = QRCodeService.generate_payment_qr(payment_url, request=request)

    context = {
        'payment': payment,
        'reference': payment.payment_reference,
        'order_reference': payment.order.order_number if payment.order else (payment.sale.sale_number if payment.sale else payment.payment_reference),
        'amount': payment.amount,
        'bank_name': bank_name,
        'account_number': account_number,
        'checkout_url': checkout_url,
        'payment_url': payment_url,
        'qr_code_data': qr_code_data,
        'expires_at': meta.get('expires_at'),
    }

    if wants_json:
        json_data = {
            'payment': _serialize_payment(payment),
            'reference': payment.payment_reference,
            'order_reference': payment.order.order_number if payment.order else (payment.sale.sale_number if payment.sale else payment.payment_reference),
            'amount': str(payment.amount),
            'bank_name': bank_name,
            'account_number': account_number,
            'checkout_url': checkout_url,
            'payment_url': payment_url,
            'qr_code_data': qr_code_data,
            'expires_at': meta.get('expires_at'),
        }
        return _json_response(data=json_data, message='Payment details retrieved.')

    return render(request, 'payments/qr_pay.html', context)



@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    POST /payments/webhooks/paystack/
    Inbound webhook receiver for Paystack events.
    Verifies cryptographic HMAC-SHA512 request signature using settings.PAYSTACK_SECRET_KEY.
    Transitions matching pending payments to COMPLETED or FAILED idempotently with row-level locks.
    """
    signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE') or request.headers.get('x-paystack-signature')
    if not signature:
        return JsonResponse({'status': False, 'message': 'Missing x-paystack-signature header'}, status=400)

    if not PaymentService.verify_paystack_signature(request.body, signature):
        return JsonResponse({'status': False, 'message': 'Invalid Paystack signature'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': False, 'message': 'Invalid JSON body'}, status=400)

    event = data.get('event', '')
    event_data = data.get('data') or {}
    reference = event_data.get('reference') or data.get('reference')
    if not reference:
        return JsonResponse({'status': False, 'message': 'Missing transaction reference in payload'}, status=400)

    raw_kobo = event_data.get('amount')
    paid_amount = None
    if raw_kobo is not None:
        try:
            paid_amount = (Decimal(str(raw_kobo)) / Decimal('100'))
        except (InvalidOperation, TypeError, ValueError):
            paid_amount = None
    gateway_status = event_data.get('status', 'success')
    currency = event_data.get('currency', 'NGN')

    result = PaymentService.confirm_webhook_payment(
        reference=reference,
        provider='paystack',
        payload=data,
        event=event,
        paid_amount=paid_amount,
        gateway_status=gateway_status,
        currency=currency,
    )

    http_status = result.get('code', 200)
    safe_result = {k: v for k, v in result.items() if k != 'payment'}
    return JsonResponse({'status': True, 'data': safe_result, 'message': result.get('message', 'Processed')}, status=http_status)


@csrf_exempt
@require_POST
def moniepoint_webhook(request):
    """
    POST /payments/webhooks/moniepoint/
    Inbound webhook receiver for Moniepoint POS / transfer events.
    Verifies cryptographic signature using settings.MONIEPOINT_SECRET_KEY.
    Transitions matching pending payments to COMPLETED or FAILED idempotently with row-level locks.
    """
    signature = (
        request.META.get('HTTP_M_SIGNATURE')
        or request.META.get('HTTP_X_MONIEPOINT_SIGNATURE')
        or request.headers.get('m-signature')
        or request.headers.get('x-moniepoint-signature')
    )
    if not signature:
        return JsonResponse({'status': False, 'message': 'Missing Moniepoint signature header'}, status=400)

    if not PaymentService.verify_moniepoint_signature(request.body, signature):
        return JsonResponse({'status': False, 'message': 'Invalid Moniepoint signature'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': False, 'message': 'Invalid JSON body'}, status=400)

    event = data.get('eventType') or data.get('event') or 'transaction.successful'
    event_data = data.get('data') or data
    reference = (
        event_data.get('merchantReference')
        or event_data.get('transactionReference')
        or event_data.get('reference')
        or event_data.get('paymentReference')
    )
    if not reference:
        return JsonResponse({'status': False, 'message': 'Missing transaction reference in payload'}, status=400)

    raw_amount = event_data.get('amount') if event_data.get('amount') is not None else event_data.get('actualAmount')
    paid_amount = None
    if raw_amount is not None:
        try:
            paid_amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError, ValueError):
            paid_amount = None
    gateway_status = event_data.get('status') or event_data.get('transactionStatus') or 'SUCCESSFUL'
    currency = event_data.get('currency', 'NGN')

    result = PaymentService.confirm_webhook_payment(
        reference=reference,
        provider='moniepoint',
        payload=data,
        event=event,
        paid_amount=paid_amount,
        gateway_status=gateway_status,
        currency=currency,
    )

    http_status = result.get('code', 200)
    safe_result = {k: v for k, v in result.items() if k != 'payment'}
    return JsonResponse({'status': True, 'data': safe_result, 'message': result.get('message', 'Processed')}, status=http_status)


def mismatches_list(request):
    """
    GET /payments/mismatches/
    Lists financial discrepancies, overpayments, partial payments, and gateway mismatches.
    Restricted to OWNER and MANAGER roles.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can view payment mismatches.', success=False, status=403)

    classification = request.GET.get('classification')
    is_resolved_param = request.GET.get('is_resolved')
    is_resolved = None
    if is_resolved_param is not None:
        is_resolved = is_resolved_param.strip().lower() in ('true', '1', 'yes')

    discrepancies = PaymentResolutionService.list_discrepancies(
        classification=classification,
        is_resolved=is_resolved,
    )

    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Viewed payment mismatches',
        description=f'Viewed payment discrepancies list (found {len(discrepancies)} records).',
        metadata={
            'total_count': len(discrepancies),
            'classification_filter': classification,
            'is_resolved_filter': is_resolved,
        },
    )

    return _json_response(
        data={
            'discrepancies': discrepancies,
            'total_count': len(discrepancies),
            'classification': classification,
        },
        message='Payment mismatches retrieved successfully.',
    )


def payment_resolve(request, payment_id):
    """
    POST /payments/<payment_id>/resolve/
    Resolves a verified payment discrepancy or mismatch.
    Restricted to OWNER and MANAGER roles.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can resolve payment discrepancies.', success=False, status=403)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type or (request.body and request.body.strip().startswith((b'{', b'['))):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()

    strategy = payload.get('strategy') or request.GET.get('strategy')
    resolution_notes = payload.get('resolution_notes') or payload.get('notes')
    amount = payload.get('amount')
    payment_method = payload.get('payment_method')
    mark_completed = bool(payload.get('mark_completed', False))

    if not strategy:
        return _json_response(message='Resolution strategy is required.', success=False, status=400)
    if not resolution_notes or not str(resolution_notes).strip():
        return _json_response(message='Resolution notes are required.', success=False, status=400)

    try:
        result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=payment_id,
            strategy=strategy,
            actor=request.user,
            resolution_notes=resolution_notes,
            amount=amount,
            payment_method=payment_method,
            mark_completed=mark_completed,
        )
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    return _json_response(data=result, message='Discrepancy resolved successfully.')


def payment_refund(request, payment_id):
    """
    POST /payments/<payment_id>/refund/
    Processes full or partial refund, multi-channel reversal, and inventory restocking.
    Strictly restricted to OWNER and MANAGER roles.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can process refunds.', success=False, status=403)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type or (request.body and request.body.strip().startswith((b'{', b'['))):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()

    amount = payload.get('amount')
    reason = payload.get('reason') or payload.get('refund_reason') or payload.get('notes')
    restock_inventory = payload.get('restock_inventory')
    if restock_inventory is None:
        restock_inventory = False
    elif isinstance(restock_inventory, str):
        restock_inventory = restock_inventory.strip().lower() in ('true', '1', 'yes')
    else:
        restock_inventory = bool(restock_inventory)

    channel = payload.get('channel')

    if not reason or not str(reason).strip():
        return _json_response(message='Refund reason is required.', success=False, status=400)

    try:
        result = PaymentRefundService.process_refund(
            payment=payment_id,
            amount=amount,
            reason=reason,
            restock_inventory=restock_inventory,
            user=request.user,
            channel=channel,
        )
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    return _json_response(data=result, message='Payment refunded successfully.')


def refunds_list(request):
    """
    GET /payments/refunds/
    Lists refunded and partially refunded payments with structured audit logs.
    Strictly restricted to OWNER and MANAGER roles.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER'):
        return _json_response(message='Only owners and managers can view payment refunds.', success=False, status=403)

    status = request.GET.get('status')
    date_from = request.GET.get('date_from') or request.GET.get('from')
    date_to = request.GET.get('date_to') or request.GET.get('to')

    refunds = PaymentRefundService.list_refunds(
        status=status,
        date_from=date_from,
        date_to=date_to,
    )

    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Viewed payment refunds',
        description=f'Viewed payment refunds list (found {len(refunds)} records).',
        metadata={
            'total_count': len(refunds),
            'status_filter': status,
            'date_from': date_from,
            'date_to': date_to,
        },
    )

    return _json_response(
        data={
            'refunds': refunds,
            'total_count': len(refunds),
            'status': status,
        },
        message='Refunds retrieved successfully.',
    )


def terminal_push(request):
    """
    POST /payments/terminal/push/
    Initiates an instant push charge to a physical or sandbox Moniepoint POS terminal.
    Restricted to staff roles (CASHIER, MANAGER, OWNER).
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)
    if getattr(request.user, 'role', None) not in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
        return _json_response(message='Only staff can initiate POS terminal charges.', success=False, status=403)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type or (request.body and request.body.strip().startswith((b'{', b'['))):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()

    target = None
    if payload.get('payment_id'):
        try:
            target = Payment.objects.get(pk=int(str(payload['payment_id'])))
        except (Payment.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Payment record not found.', success=False, status=404)
    elif payload.get('sale_id'):
        try:
            target = Sale.objects.get(pk=int(str(payload['sale_id'])))
        except (Sale.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Sale not found.', success=False, status=404)
    elif payload.get('order_id'):
        try:
            target = Order.objects.get(pk=int(str(payload['order_id'])))
        except (Order.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Order not found.', success=False, status=404)
    elif payload.get('target_id'):
        target_id_str = str(payload['target_id']).strip()
        target_type = str(payload.get('target_type', '')).strip().lower()
        try:
            numeric_id = int(target_id_str)
            if target_type in ('sale', 'pos'):
                target = Sale.objects.filter(pk=numeric_id).first()
            elif target_type in ('order', 'ord'):
                target = Order.objects.filter(pk=numeric_id).first()
            elif target_type == 'payment':
                target = Payment.objects.filter(pk=numeric_id).first()
            else:
                target = Sale.objects.filter(pk=numeric_id).first() or Order.objects.filter(pk=numeric_id).first()
        except (TypeError, ValueError):
            target = None

    if target is None:
        return _json_response(message='A valid Payment, Sale, or Order target is required.', success=False, status=400)

    terminal_id = payload.get('terminal_id') or payload.get('terminalId') or payload.get('terminal_serial') or payload.get('terminalSerial')
    amount = payload.get('amount')
    description = payload.get('description')
    payment_method = payload.get('payment_method') or payload.get('paymentMethod') or 'CARD_PURCHASE'

    try:
        result = PaymentService.push_to_pos(
            target=target,
            terminal_id=terminal_id,
            amount=amount,
            cashier=request.user,
            description=description,
            payment_method=payment_method,
        )
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    http_status = 200 if result.get('success') else 502
    return _json_response(
        data=result,
        message=result.get('message', 'POS terminal charge initiated successfully.'),
        success=result.get('success', True),
        status=http_status,
    )


def terminal_status(request, reference):
    """
    GET /payments/terminal/<reference>/status/
    GET /payments/pos-status/<reference>/
    Polls current Moniepoint POS terminal charge status for a reference.
    Automatically finalizes draft sales and deducts inventory on SUCCESS.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    user_role = getattr(request.user, 'role', None)
    is_staff = user_role in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')

    result = PaymentService.poll_terminal_status(reference=reference, cashier=request.user if is_staff else None)
    if not result.get('found'):
        return _json_response(data=result, message='Payment reference not found.', success=False, status=404)

    # Customer data isolation
    if not is_staff:
        payment_id = result.get('payment_id')
        payment_obj = Payment.objects.filter(pk=payment_id).first()
        if not payment_obj or (
            payment_obj.customer_id != request.user.id
            and getattr(payment_obj.sale, 'customer_id', None) != request.user.id
            and getattr(payment_obj.order, 'customer_id', None) != request.user.id
        ):
            return _json_response(message='You do not have permission to access this payment transaction.', success=False, status=403)

    is_success = result.get('status') == 'SUCCESS' or result.get('is_completed') is True
    return _json_response(
        data=result,
        message='Payment confirmed successfully.' if is_success else result.get('message', 'Terminal status retrieved successfully.'),
        success=True,
    )


def paystack_initialize(request):
    """
    POST /payments/paystack/initialize/
    Initializes a Paystack standard/inline checkout session and returns authorization URL.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)
    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    payload = {}
    content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
    if 'application/json' in content_type or (request.body and request.body.strip().startswith((b'{', b'['))):
        parsed_payload, err = _parse_json_body(request)
        if err:
            return _json_response(message='Validation failed.', success=False, status=400, errors=err)
        payload = parsed_payload or {}
    elif getattr(request, 'POST', None):
        payload = request.POST.dict()

    target = None
    if payload.get('order_id'):
        try:
            target = Order.objects.get(pk=int(str(payload['order_id'])))
        except (Order.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Order not found.', success=False, status=404)
    elif payload.get('sale_id'):
        try:
            target = Sale.objects.get(pk=int(str(payload['sale_id'])))
        except (Sale.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Sale not found.', success=False, status=404)
    elif payload.get('payment_id'):
        try:
            target = Payment.objects.get(pk=int(str(payload['payment_id'])))
        except (Payment.DoesNotExist, TypeError, ValueError):
            return _json_response(message='Payment record not found.', success=False, status=404)
    elif payload.get('target_id'):
        target_id_str = str(payload['target_id']).strip()
        try:
            numeric_id = int(target_id_str)
            target = Order.objects.filter(pk=numeric_id).first() or Sale.objects.filter(pk=numeric_id).first()
        except (TypeError, ValueError):
            target = None

    if target is None:
        return _json_response(message='A valid Order, Sale, or Payment target is required.', success=False, status=400)

    # Authorization / customer isolation
    user_role = getattr(request.user, 'role', None)
    if isinstance(target, Order) and user_role not in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
        if target.customer_id != request.user.id:
            return _json_response(message='You can only initialize checkout for your own orders.', success=False, status=403)
    elif isinstance(target, Sale) and user_role not in ('OWNER', 'MANAGER', 'CASHIER', 'STAFF'):
        return _json_response(message='Staff permission required.', success=False, status=403)

    email = payload.get('email') or getattr(request.user, 'email', None)
    amount = payload.get('amount')
    callback_url = payload.get('callback_url')

    try:
        result = PaymentService.initialize_paystack_checkout(
            target=target,
            email=email,
            amount=amount,
            callback_url=callback_url,
        )
    except ValidationError as exc:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors=exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages},
        )

    http_status = 200 if result.get('success') else 502
    return _json_response(
        data=result,
        message=result.get('message', 'Paystack transaction initialized successfully.'),
        success=result.get('success', True),
        status=http_status,
    )
