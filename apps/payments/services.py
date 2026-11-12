import hashlib
import hmac
import os
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity, log_model_activity
from apps.orders.models import Order
from apps.sales.models import Sale

from .models import Payment
from .verification import PaymentVerificationStatus


class PaymentService:
    """Centralized rules for safe Payments domain operations."""

    CONFIRMATION_ROLES = ('OWNER', 'MANAGER')

    LEGACY_PAYMENT_METHODS = {
        'TRANSFER': Payment.PaymentMethod.BANK_TRANSFER,
        'BANK_TRANSFER': Payment.PaymentMethod.BANK_TRANSFER,
    }

    @classmethod
    def normalize_payment_method(cls, value):
        if value is None:
            raise ValidationError({'payment_method': 'Payment method is required.'})

        normalized = str(value).strip().upper()
        if normalized in cls.LEGACY_PAYMENT_METHODS:
            return cls.LEGACY_PAYMENT_METHODS[normalized]

        valid_methods = {choice.value for choice in Payment.PaymentMethod}
        if normalized in valid_methods:
            return normalized

        raise ValidationError({'payment_method': 'Invalid payment method.'})

    @classmethod
    def normalize_payment_status(cls, value):
        default = Payment.PaymentStatus.PENDING
        if value in (None, ''):
            return default

        normalized = str(value).strip().upper()
        valid_statuses = {choice.value for choice in Payment.PaymentStatus}
        if normalized in valid_statuses:
            return normalized

        raise ValidationError({'payment_status': 'Invalid payment status.'})

    @classmethod
    def resolve_transaction_context(cls, sale=None, order=None):
        if sale and order:
            raise ValidationError(
                {'transaction': 'A payment cannot be linked to both a sale and an order at the same time.'}
            )
        if not sale and not order:
            raise ValidationError({'transaction': 'A payment must belong to either a sale or an order.'})
        return sale, order

    @classmethod
    def validate_amount(cls, amount):
        if amount is None:
            raise ValidationError({'amount': 'Payment amount is required.'})

        try:
            numeric_amount = Decimal(str(amount))
        except (TypeError, ValueError, ArithmeticError):
            raise ValidationError({'amount': 'Amount must be a valid monetary value.'})

        if numeric_amount < 0:
            raise ValidationError({'amount': 'Payment amount cannot be negative.'})
        if numeric_amount == Decimal('0.00'):
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})
        if numeric_amount.as_tuple().exponent < -2:
            raise ValidationError({'amount': 'Amount cannot have more than two decimal places.'})
        return numeric_amount

    @classmethod
    def validate_customer_match(cls, customer, sale=None, order=None):
        if customer is None:
            return

        if customer.role != 'CUSTOMER':
            raise ValidationError({'customer': 'Only customers can be assigned to payment records.'})

        if sale and sale.customer_id and sale.customer_id != customer.id:
            raise ValidationError({'customer': 'Customer does not match the associated sale.'})

        if order and order.customer_id and order.customer_id != customer.id:
            raise ValidationError({'customer': 'Customer does not match the associated order.'})

    @classmethod
    def validate_transaction_exists(cls, sale=None, order=None):
        if sale is not None and sale.pk is None:
            raise ValidationError({'sale': 'Sale not found.'})
        if order is not None and order.pk is None:
            raise ValidationError({'order': 'Order not found.'})

        if sale is not None:
            try:
                Sale.objects.get(pk=sale.pk)
            except Sale.DoesNotExist:
                raise ValidationError({'sale': 'Sale not found.'})

        if order is not None:
            try:
                Order.objects.get(pk=order.pk)
            except Order.DoesNotExist:
                raise ValidationError({'order': 'Order not found.'})

        return sale, order

    @classmethod
    def validate_cashier(cls, cashier):
        if cashier is None:
            return

        if cashier.role not in ['CASHIER', 'MANAGER', 'OWNER']:
            raise ValidationError({'cashier': 'Only staff can process payment records.'})

    @classmethod
    def validate_confirmation_actor(cls, actor):
        if actor is None or not getattr(actor, 'is_authenticated', False):
            raise ValidationError({'confirmed_by': 'An authenticated confirmation actor is required.'})
        if getattr(actor, 'role', None) not in cls.CONFIRMATION_ROLES:
            raise ValidationError({'confirmed_by': 'Only owners and managers can confirm payments.'})

    @classmethod
    @transaction.atomic
    def confirm_payment(cls, payment_id, confirmed_by):
        cls.validate_confirmation_actor(confirmed_by)
        try:
            payment = Payment.objects.select_for_update().get(pk=payment_id)
        except Payment.DoesNotExist:
            raise ValidationError({'payment': 'Payment not found.'})

        if payment.payment_status == Payment.PaymentStatus.COMPLETED:
            return payment
        if payment.payment_status != Payment.PaymentStatus.PENDING:
            raise ValidationError({'payment_status': 'Only PENDING payments can be confirmed.'})

        payment.payment_status = Payment.PaymentStatus.COMPLETED
        payment.save(update_fields=['payment_status', 'updated_at'])
        log_model_activity(
            actor=confirmed_by,
            action_type=ActivityLog.ActionType.PAYMENT,
            action_label='Confirmed payment',
            description=f'Payment {payment.payment_reference} was confirmed.',
            model_instance=payment,
            metadata={
                'previous_status': Payment.PaymentStatus.PENDING,
                'new_status': Payment.PaymentStatus.COMPLETED,
            },
        )
        return payment

    @classmethod
    def normalize_idempotency_key(cls, value):
        if value in (None, ''):
            return None
        key = str(value).strip()
        if not key:
            return None
        if len(key) > 120:
            raise ValidationError({'idempotency_key': 'Idempotency key cannot exceed 120 characters.'})
        return key

    @classmethod
    def validate_idempotency_match(cls, existing, candidate):
        fields = (
            ('sale_id', 'sale'),
            ('order_id', 'order'),
            ('customer_id', 'customer'),
            ('cashier_id', 'cashier'),
            ('amount', 'amount'),
            ('payment_method', 'payment_method'),
            ('payment_status', 'payment_status'),
            ('transaction_reference', 'transaction_reference'),
            ('transaction_metadata', 'transaction_metadata'),
            ('notes', 'notes'),
        )
        for existing_field, label in fields:
            if getattr(existing, existing_field) != getattr(candidate, existing_field):
                raise ValidationError({'idempotency_key': f'Idempotency key is already used for different {label} data.'})

    @classmethod
    def get_idempotent_payment(cls, idempotency_key, candidate):
        if not idempotency_key:
            return None
        existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            cls.validate_idempotency_match(existing, candidate)
        return existing

    @classmethod
    def get_transaction_balance(cls, transaction):
        """Calculate payment totals for an existing Order or Sale without mutation."""
        if not isinstance(transaction, (Order, Sale)) or transaction.pk is None:
            raise ValidationError({'transaction': 'An existing order or sale is required.'})

        relation_field = 'order_id' if isinstance(transaction, Order) else 'sale_id'
        payments = Payment.objects.filter(**{relation_field: transaction.pk})
        totals = payments.aggregate(
            completed_amount=Sum(
                'amount',
                filter=Q(payment_status=Payment.PaymentStatus.COMPLETED),
            ),
            pending_amount=Sum(
                'amount',
                filter=Q(payment_status=Payment.PaymentStatus.PENDING),
            ),
            failed_amount=Sum(
                'amount',
                filter=Q(payment_status=Payment.PaymentStatus.FAILED),
            ),
            refunded_amount=Sum(
                'amount',
                filter=Q(payment_status=Payment.PaymentStatus.REFUNDED),
            ),
        )

        zero = Decimal('0.00')
        total = transaction.total
        completed_amount = totals['completed_amount'] or zero
        pending_amount = totals['pending_amount'] or zero
        failed_amount = totals['failed_amount'] or zero
        refunded_amount = totals['refunded_amount'] or zero

        return {
            'transaction_total': total,
            'completed_amount': completed_amount,
            'pending_amount': pending_amount,
            'failed_amount': failed_amount,
            'refunded_amount': refunded_amount,
            'outstanding_amount': max(total - completed_amount, zero),
            'overpaid_amount': max(completed_amount - total, zero),
        }

    @classmethod
    def build_payment(
        cls,
        *,
        payment_reference,
        idempotency_key=None,
        sale=None,
        order=None,
        customer=None,
        cashier=None,
        amount,
        payment_method,
        payment_status=None,
        transaction_reference='',
        transaction_metadata=None,
        notes='',
    ):
        sale, order = cls.resolve_transaction_context(sale=sale, order=order)
        sale, order = cls.validate_transaction_exists(sale=sale, order=order)
        normalized_method = cls.normalize_payment_method(payment_method)
        normalized_status = cls.normalize_payment_status(payment_status)
        numeric_amount = cls.validate_amount(amount)

        if customer is None:
            customer = sale.customer if sale else order.customer

        cls.validate_customer_match(customer, sale=sale, order=order)
        cls.validate_cashier(cashier)

        payment = Payment(
            payment_reference=payment_reference,
            idempotency_key=idempotency_key,
            sale=sale,
            order=order,
            customer=customer,
            cashier=cashier,
            amount=numeric_amount,
            payment_method=normalized_method,
            payment_status=normalized_status,
            transaction_reference=transaction_reference or '',
            transaction_metadata=transaction_metadata or {},
            notes=notes or '',
        )
        validation_exclusions = ['idempotency_key']
        if idempotency_key:
            validation_exclusions.append('payment_reference')
        payment.full_clean(exclude=validation_exclusions)
        return payment

    @classmethod
    @transaction.atomic
    def create_payment(
        cls,
        *,
        payment_reference,
        idempotency_key=None,
        sale=None,
        order=None,
        customer=None,
        cashier=None,
        amount,
        payment_method,
        payment_status=None,
        transaction_reference='',
        transaction_metadata=None,
        notes='',
        allow_completed=False,
    ):
        normalized_key = cls.normalize_idempotency_key(idempotency_key)
        normalized_status = cls.normalize_payment_status(payment_status)
        if normalized_status == Payment.PaymentStatus.COMPLETED and not allow_completed:
            raise ValidationError({'payment_status': 'Payments must be confirmed separately after creation.'})
        payment = cls.build_payment(
            payment_reference=payment_reference,
            idempotency_key=normalized_key,
            sale=sale,
            order=order,
            customer=customer,
            cashier=cashier,
            amount=amount,
            payment_method=payment_method,
            payment_status=normalized_status,
            transaction_reference=transaction_reference,
            transaction_metadata=transaction_metadata,
            notes=notes,
        )
        existing = cls.get_idempotent_payment(normalized_key, payment)
        if existing is not None:
            return existing

        try:
            with transaction.atomic():
                payment.save()
        except (IntegrityError, ValidationError):
            existing = cls.get_idempotent_payment(normalized_key, payment)
            if existing is None:
                raise
            return existing
        return payment

    @classmethod
    def verify_payment(cls, payment, provider='mock', **kwargs):
        """Execute non-destructive verification for a payment record."""
        from .verification import PaymentVerificationService
        return PaymentVerificationService.verify_payment_transaction(payment, provider=provider, **kwargs)

    @classmethod
    def verify_paystack_signature(cls, raw_body, signature_header: str, secret_key: str = None) -> bool:
        """
        Verify Paystack HMAC-SHA512 webhook signature.
        """
        key = (secret_key or getattr(settings, 'PAYSTACK_SECRET_KEY', '') or os.getenv('PAYSTACK_SECRET_KEY', '')).strip()
        if not key or not signature_header:
            return False
        clean_sig = str(signature_header).strip()
        if clean_sig.lower().startswith('sha512='):
            clean_sig = clean_sig[7:].strip()
        body_bytes = raw_body.encode('utf-8') if isinstance(raw_body, str) else raw_body
        computed = hmac.new(key.encode('utf-8'), body_bytes, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed.lower(), clean_sig.lower())

    @classmethod
    def verify_moniepoint_signature(cls, raw_body, signature_header: str, secret_key: str = None) -> bool:
        """
        Verify Moniepoint HMAC signature (supporting HMAC-SHA256 and HMAC-SHA512).
        """
        key = (
            secret_key
            or getattr(settings, 'MONIEPOINT_SECRET_KEY', '')
            or getattr(settings, 'MONIEPOINT_API_KEY', '')
            or os.getenv('MONIEPOINT_SECRET_KEY', '')
        ).strip()
        if not key or not signature_header:
            return False
        clean_sig = str(signature_header).strip()
        if clean_sig.lower().startswith('sha256='):
            clean_sig = clean_sig[7:].strip()
        elif clean_sig.lower().startswith('sha512='):
            clean_sig = clean_sig[7:].strip()
        body_bytes = raw_body.encode('utf-8') if isinstance(raw_body, str) else raw_body
        computed_sha256 = hmac.new(key.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed_sha256.lower(), clean_sig.lower()):
            return True
        computed_sha512 = hmac.new(key.encode('utf-8'), body_bytes, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed_sha512.lower(), clean_sig.lower())

    @classmethod
    @transaction.atomic
    def confirm_webhook_payment(
        cls,
        *,
        reference: str,
        provider: str,
        payload: dict = None,
        event: str = 'charge.success',
        paid_amount=None,
        gateway_status: str = 'success',
        currency: str = 'NGN',
    ) -> dict:
        """
        Idempotent webhook payment ingestion and double-payment guard.
        Uses database row locking (select_for_update), amount matching,
        and safe order/sale lifecycle advancement.
        """
        clean_ref = str(reference or '').strip()
        if not clean_ref:
            return {
                'status': 'error',
                'found': False,
                'is_completed': False,
                'message': 'No payment reference provided.',
                'code': 400,
            }

        payment = Payment.objects.select_for_update().filter(
            Q(transaction_reference=clean_ref) | Q(payment_reference=clean_ref)
        ).first()

        if not payment:
            try:
                payment = Payment.objects.select_for_update().get(pk=int(clean_ref))
            except (Payment.DoesNotExist, ValueError, TypeError):
                payment = None

        if not payment:
            return {
                'status': 'not_found',
                'found': False,
                'is_completed': False,
                'message': f'Payment reference "{clean_ref}" not found.',
                'code': 404,
            }

        # 1. Idempotency Guard: if ALREADY COMPLETED, immediately return 200 without mutations
        if payment.payment_status == Payment.PaymentStatus.COMPLETED:
            return {
                'status': 'already_completed',
                'payment': payment,
                'payment_id': payment.id,
                'reference': payment.payment_reference,
                'is_completed': True,
                'has_discrepancy': False,
                'message': f'Payment {payment.payment_reference} is already completed. Idempotent webhook ignored.',
                'code': 200,
            }

        # 2. Amount Matching Guard
        dec_paid = None
        has_amount_mismatch = False
        if paid_amount is not None:
            try:
                dec_paid = Decimal(str(paid_amount)).quantize(Decimal('0.01'))
                if dec_paid != payment.amount:
                    # Minor unit (kobo) conversion fallback
                    if (dec_paid / Decimal('100')).quantize(Decimal('0.01')) == payment.amount:
                        dec_paid = (dec_paid / Decimal('100')).quantize(Decimal('0.01'))
                    else:
                        has_amount_mismatch = True
            except Exception:
                has_amount_mismatch = True

        if has_amount_mismatch:
            meta = dict(payment.transaction_metadata or {})
            discrepancy_note = f'Amount mismatch: expected {payment.amount}, received {dec_paid}.'
            meta['webhook_discrepancy'] = discrepancy_note
            meta['webhook_verification_status'] = PaymentVerificationStatus.MISMATCH.value
            if payload:
                meta['webhook_mismatch_payload'] = payload
            payment.transaction_metadata = meta
            payment.save(update_fields=['transaction_metadata', 'updated_at'])

            log_activity(
                actor=None,
                action_type=ActivityLog.ActionType.UPDATED,
                action_label='Webhook payment mismatch',
                description=f'Webhook reported amount mismatch for payment {payment.payment_reference}: expected {payment.amount}, received {dec_paid}.',
                related_object=payment,
                metadata={
                    'payment_id': payment.id,
                    'reference': payment.payment_reference,
                    'expected_amount': str(payment.amount),
                    'received_amount': str(dec_paid),
                    'provider': provider,
                    'discrepancy': discrepancy_note,
                },
            )

            return {
                'status': 'amount_mismatch',
                'payment': payment,
                'payment_id': payment.id,
                'reference': payment.payment_reference,
                'is_completed': False,
                'has_discrepancy': True,
                'message': discrepancy_note,
                'code': 200,
            }

        # 3. Gateway Status Check
        norm_status = str(gateway_status or 'success').strip().lower()
        is_success = norm_status in ('success', 'successful', 'approved', 'paid', 'completed')
        is_failure = norm_status in ('failed', 'declined', 'cancelled', 'abandoned', 'error')

        if is_failure:
            payment.payment_status = Payment.PaymentStatus.FAILED
            meta = dict(payment.transaction_metadata or {})
            meta['webhook_failed_status'] = norm_status
            if payload:
                meta['webhook_failure_payload'] = payload
            payment.transaction_metadata = meta
            payment.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

            log_activity(
                actor=None,
                action_type=ActivityLog.ActionType.PAYMENT,
                action_label='Webhook payment failed',
                description=f'Webhook reported payment failure for {payment.payment_reference} ({norm_status}).',
                related_object=payment,
                metadata={
                    'payment_id': payment.id,
                    'reference': payment.payment_reference,
                    'provider': provider,
                    'gateway_status': norm_status,
                },
            )

            return {
                'status': 'failed',
                'payment': payment,
                'payment_id': payment.id,
                'reference': payment.payment_reference,
                'is_completed': False,
                'has_discrepancy': False,
                'message': f'Payment marked FAILED based on webhook status {norm_status}.',
                'code': 200,
            }

        if not is_success:
            return {
                'status': 'ignored',
                'payment': payment,
                'payment_id': payment.id,
                'reference': payment.payment_reference,
                'is_completed': False,
                'message': f'Webhook event with status {norm_status} ignored.',
                'code': 200,
            }

        # 4. Successful confirmation
        payment.payment_status = Payment.PaymentStatus.COMPLETED
        meta = dict(payment.transaction_metadata or {})
        meta['webhook_confirmed'] = True
        meta['webhook_provider'] = provider
        meta['webhook_event'] = event
        meta['webhook_timestamp'] = timezone.now().isoformat()
        meta['verified_amount'] = str(dec_paid or payment.amount)
        payment.transaction_metadata = meta
        payment.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

        # 5. Advance target Order / Sale status safely
        if payment.order:
            order = payment.order
            order_changed = False
            if order.payment_status != Order.PaymentStatus.CONFIRMED:
                order.payment_status = Order.PaymentStatus.CONFIRMED
                order_changed = True
            if order.status == Order.OrderStatus.PENDING:
                try:
                    order.transition_to(Order.OrderStatus.CONFIRMED)
                except Exception:
                    order.status = Order.OrderStatus.CONFIRMED
                order_changed = True

            if order_changed:
                order.save(update_fields=['status', 'payment_status'])

        if payment.sale_id:
            from apps.sales.models import Sale
            try:
                sale = Sale.objects.select_for_update().get(pk=payment.sale_id)
                if sale.status == Sale.SaleStatus.DRAFT:
                    if sale.amount_received is None:
                        sale.amount_received = payment.amount
                    if sale.change_amount is None:
                        sale.change_amount = Decimal('0.00')
                    sale.complete_sale()
                elif sale.payment_status != Sale.PaymentStatus.COMPLETED:
                    sale.payment_status = Sale.PaymentStatus.COMPLETED
                    sale.save(update_fields=['payment_status', 'updated_at'])
            except Exception as exc:
                logger.error(f"Error finalizing sale {payment.sale_id} on payment confirmation: {exc}")

        # 6. Notifications
        try:
            from apps.notifications.services import NotificationService
            from apps.notifications.models import Notification
            recipient = payment.customer or (payment.order.customer if payment.order else None) or (payment.sale.customer if payment.sale else None)
            if recipient:
                NotificationService.create_notification(
                    recipient=recipient,
                    notification_type=Notification.NotificationType.PAYMENT,
                    title='Payment Confirmed',
                    message=f'Your payment of ₦{payment.amount:,.2f} (ref: {payment.payment_reference}) was successfully confirmed via {provider.upper()}.',
                    related_object=payment,
                )
        except Exception:
            pass

        # 7. Audit activity log
        log_activity(
            actor=None,
            action_type=ActivityLog.ActionType.PAYMENT,
            action_label='Webhook payment confirmed',
            description=f'Webhook confirmed payment {payment.payment_reference} via {provider.upper()}.',
            related_object=payment,
            metadata={
                'payment_id': payment.id,
                'reference': payment.payment_reference,
                'amount': str(payment.amount),
                'provider': provider,
                'event': event,
            },
        )

        return {
            'status': 'completed',
            'payment': payment,
            'payment_id': payment.id,
            'reference': payment.payment_reference,
            'is_completed': True,
            'has_discrepancy': False,
            'message': f'Payment {payment.payment_reference} successfully confirmed via {provider.upper()} webhook.',
            'code': 200,
        }

    @classmethod
    def resolve_discrepancy(cls, *args, **kwargs):
        """Execute discrepancy resolution workflow (Phase 6)."""
        from .resolution import PaymentResolutionService
        return PaymentResolutionService.resolve_discrepancy(*args, **kwargs)

    @classmethod
    def list_discrepancies(cls, *args, **kwargs):
        """List financial discrepancies and mismatches (Phase 6)."""
        from .resolution import PaymentResolutionService
        return PaymentResolutionService.list_discrepancies(*args, **kwargs)

    @classmethod
    def process_refund(cls, *args, **kwargs):
        """Execute payment refund and reversal workflow (Phase 7)."""
        from .refund_service import PaymentRefundService
        return PaymentRefundService.process_refund(*args, **kwargs)

    @classmethod
    def list_refunds(cls, *args, **kwargs):
        """List refunded payments and reversals (Phase 7)."""
        from .refund_service import PaymentRefundService
        return PaymentRefundService.list_refunds(*args, **kwargs)

    @classmethod
    def push_to_pos(cls, *args, **kwargs):
        """Initiate Moniepoint POS terminal charge push (Phase 4B)."""
        from .terminal_service import MoniepointTerminalService
        return MoniepointTerminalService.push_to_pos(*args, **kwargs)

    @classmethod
    def poll_terminal_status(cls, *args, **kwargs):
        """Poll Moniepoint POS terminal charge status (Phase 4B)."""
        from .terminal_service import MoniepointTerminalService
        return MoniepointTerminalService.poll_terminal_status(*args, **kwargs)

    @classmethod
    def initialize_paystack_checkout(cls, *args, **kwargs):
        """Initialize Paystack online checkout transaction (Phase 4A)."""
        from .paystack_service import PaystackCheckoutService
        return PaystackCheckoutService.initialize_transaction(*args, **kwargs)

    @classmethod
    def generate_payment_qr(cls, *args, **kwargs):
        """Generate in-memory dynamic payment QR code as PNG Base64 Data URI."""
        from .qr_service import generate_payment_qr
        return generate_payment_qr(*args, **kwargs)

    @classmethod
    def decode_qr_data(cls, *args, **kwargs):
        """Decode QR payload from Base64 Data URI or image bytes."""
        from .qr_service import decode_qr_data
        return decode_qr_data(*args, **kwargs)


def generate_payment_qr(*args, **kwargs):
    """Module-level helper to generate dynamic payment QR codes."""
    from .qr_service import generate_payment_qr as _gen_qr
    return _gen_qr(*args, **kwargs)


def decode_qr_data(*args, **kwargs):
    """Module-level helper to decode dynamic payment QR code data."""
    from .qr_service import decode_qr_data as _dec_qr
    return _dec_qr(*args, **kwargs)
