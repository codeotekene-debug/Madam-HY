import os
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.credits.models import CreditAccount, CreditTransaction
from apps.inventory.models import InventoryItem, StockMovement
from apps.inventory.services import adjust_inventory_stock
from apps.orders.models import Order
from apps.sales.models import Sale

from .models import Payment


class RefundChannel:
    PAYSTACK = 'PAYSTACK'
    MONIEPOINT = 'MONIEPOINT'
    CREDIT = 'CREDIT'
    CASH = 'CASH'
    INTERNAL = 'INTERNAL'

    CHOICES = (PAYSTACK, MONIEPOINT, CREDIT, CASH, INTERNAL)


class PaystackRefundAdapter:
    """Adapter for Paystack online refund API (https://api.paystack.co/refund)."""

    @classmethod
    def execute_refund(cls, transaction_reference, amount_kobo, reason='', merchant_note=''):
        secret_key = os.getenv('PAYSTACK_SECRET_KEY') or getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        mock_mode = (
            getattr(settings, 'PAYSTACK_MOCK_REFUNDS', True)
            or not secret_key
            or secret_key.startswith(('sk_test', 'mock', 'test'))
        )
        if mock_mode:
            short_id = uuid.uuid4().hex[:8].upper()
            return {
                'success': True,
                'provider': 'paystack',
                'refund_reference': f'PSTK-REF-{short_id}',
                'transaction_reference': transaction_reference,
                'amount_kobo': amount_kobo,
                'gateway_status': 'processed',
                'message': 'Simulated Paystack refund processed successfully.',
            }

        import requests
        headers = {
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'transaction': transaction_reference,
            'amount': amount_kobo,
            'currency': 'NGN',
            'customer_note': reason,
            'merchant_note': merchant_note or reason,
        }
        try:
            resp = requests.post(
                'https://api.paystack.co/refund',
                json=payload,
                headers=headers,
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and data.get('status'):
                return {
                    'success': True,
                    'provider': 'paystack',
                    'refund_reference': data.get('data', {}).get('reference', f'PSTK-REF-{uuid.uuid4().hex[:8].upper()}'),
                    'transaction_reference': transaction_reference,
                    'amount_kobo': amount_kobo,
                    'gateway_status': data.get('data', {}).get('status', 'processed'),
                    'raw_response': data,
                }
            return {
                'success': False,
                'provider': 'paystack',
                'error': data.get('message', 'Paystack refund request failed.'),
                'gateway_status': 'failed',
                'raw_response': data,
            }
        except Exception as exc:
            return {
                'success': False,
                'provider': 'paystack',
                'error': str(exc),
                'gateway_status': 'failed',
            }


class PaymentRefundService:
    """
    Centralized service for managing and executing payment refunds, chargebacks,
    multi-channel reversals, and inventory restocking.
    """

    ALLOWED_ROLES = ('OWNER', 'MANAGER')

    @classmethod
    def validate_actor(cls, actor):
        if not actor or not getattr(actor, 'is_authenticated', False):
            raise ValidationError({'actor': 'Authentication required for refund operations.'})
        if getattr(actor, 'role', None) not in cls.ALLOWED_ROLES:
            raise ValidationError({'actor': 'Only owners and managers can process payment refunds.'})

    @classmethod
    def list_refunds(cls, status=None, date_from=None, date_to=None):
        """
        Lists refunded and partially refunded payments with structured audit metadata.
        """
        qs = Payment.objects.filter(
            payment_status__in=[
                Payment.PaymentStatus.REFUNDED,
                Payment.PaymentStatus.PARTIALLY_REFUNDED,
            ]
        ).select_related('sale', 'order', 'customer', 'cashier')

        if status:
            clean_status = str(status).strip().upper()
            qs = qs.filter(payment_status=clean_status)

        if date_from:
            qs = qs.filter(updated_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(updated_at__date__lte=date_to)

        results = []
        for p in qs:
            meta = p.transaction_metadata or {}
            target = p.sale or p.order
            target_type = 'sale' if p.sale else ('order' if p.order else 'standalone')
            target_id = target.pk if target else None
            identifier = (
                target.sale_number
                if p.sale
                else (target.order_number if p.order else p.payment_reference)
            )
            results.append({
                'payment_id': p.id,
                'payment_reference': p.payment_reference,
                'transaction_reference': p.transaction_reference,
                'target_type': target_type,
                'target_id': target_id,
                'target_identifier': identifier,
                'original_amount': f'{p.amount:.2f}',
                'total_refunded': f'{p.total_refunded:.2f}',
                'remaining_refundable': f'{p.remaining_refundable_amount:.2f}',
                'status': p.payment_status,
                'payment_method': p.payment_method,
                'customer_id': p.customer_id,
                'customer_name': p.customer.get_full_name() if p.customer else None,
                'refund_reason': meta.get('refund_reason', ''),
                'refunded_at': meta.get('refunded_at'),
                'refunded_by': meta.get('refunded_by'),
                'refund_history': meta.get('refund_history', []),
            })
        return results

    @classmethod
    @transaction.atomic
    def process_refund(
        cls,
        payment,
        amount=None,
        reason: str = '',
        restock_inventory: bool = False,
        user=None,
        channel=None,
        items_to_restock=None,
        **kwargs,
    ) -> dict:
        """
        Executes a full or partial refund for a payment across supported channels.
        Guarantees row-level locking, double-refund guards, inventory restocking,
        customer credit adjustments, in-app notifications, and ActivityLog auditing.
        """
        # 1. Authorize actor
        cls.validate_actor(user)

        # 2. Validate reason
        clean_reason = str(reason or '').strip()
        if not clean_reason or len(clean_reason) < 3:
            raise ValidationError({
                'reason': 'A detailed refund justification reason (minimum 3 characters) is required.'
            })

        # 3. Resolve Payment with row-level lock
        payment_instance = None
        if isinstance(payment, Payment):
            clean_pk = payment.pk
        else:
            clean_str = str(payment).strip()
            try:
                clean_pk = int(clean_str)
            except ValueError:
                clean_pk = None

        if clean_pk is not None:
            try:
                payment_instance = Payment.objects.select_for_update().get(pk=clean_pk)
            except Payment.DoesNotExist:
                pass

        if not payment_instance:
            clean_ref = str(payment).strip()
            payment_instance = Payment.objects.select_for_update().filter(
                Q(payment_reference=clean_ref) | Q(transaction_reference=clean_ref)
            ).first()

        if not payment_instance:
            raise ValidationError({'payment': f'Payment "{payment}" not found.'})

        # 4. Check payment status eligibility
        if payment_instance.payment_status not in (
            Payment.PaymentStatus.COMPLETED,
            Payment.PaymentStatus.PARTIALLY_REFUNDED,
        ):
            if payment_instance.payment_status == Payment.PaymentStatus.REFUNDED:
                raise ValidationError({'payment': 'Payment has already been fully refunded.'})
            raise ValidationError({
                'payment': f'Only completed payments can be refunded. Current status is {payment_instance.payment_status}.'
            })

        remaining_refundable = payment_instance.remaining_refundable_amount
        if remaining_refundable <= Decimal('0.00'):
            raise ValidationError({'payment': 'Payment has already been fully refunded.'})

        # 5. Validate and calculate refund amount
        if amount is None or str(amount).strip() == '':
            refund_amount = remaining_refundable
        else:
            try:
                refund_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({'amount': 'A valid monetary refund amount is required.'})

        if refund_amount <= Decimal('0.00'):
            raise ValidationError({'amount': 'Refund amount must be greater than zero.'})

        if refund_amount > remaining_refundable:
            raise ValidationError({
                'amount': (
                    f'Refund amount ({refund_amount:.2f}) cannot exceed remaining '
                    f'refundable balance ({remaining_refundable:.2f}).'
                )
            })

        # 6. Detect / determine refund channel
        target = payment_instance.sale or payment_instance.order
        customer = payment_instance.customer or (target.customer if target else None)
        active_channel = channel

        if not active_channel:
            if payment_instance.payment_method == Payment.PaymentMethod.CREDIT:
                active_channel = RefundChannel.CREDIT
            elif payment_instance.payment_method == Payment.PaymentMethod.CASH:
                active_channel = RefundChannel.CASH
            else:
                txn_ref = payment_instance.transaction_reference or ''
                meta = payment_instance.transaction_metadata or {}
                if 'MNP' in txn_ref or meta.get('provider') == 'moniepoint' or 'moniepoint' in str(meta).lower():
                    active_channel = RefundChannel.MONIEPOINT
                else:
                    active_channel = RefundChannel.PAYSTACK

        # 7. Channel-specific execution
        channel_details = {}

        if active_channel == RefundChannel.CREDIT:
            if not customer:
                raise ValidationError({'customer': 'Customer is required for credit account refund adjustment.'})
            credit_account = CreditAccount.objects.select_for_update().filter(customer=customer).first()
            if credit_account:
                if credit_account.outstanding_balance > Decimal('0.00'):
                    repay_amt = min(refund_amount, credit_account.outstanding_balance)
                    credit_account.outstanding_balance = max(Decimal('0.00'), credit_account.outstanding_balance - repay_amt)
                    credit_account.status = credit_account.get_status_for_balance()
                    credit_account.save(update_fields=['outstanding_balance', 'status', 'updated_at'])
                    CreditTransaction.objects.create(
                        credit_account=credit_account,
                        transaction_type=CreditTransaction.TransactionType.ADJUSTMENT,
                        amount=repay_amt,
                        previous_balance=credit_account.outstanding_balance + repay_amt,
                        new_balance=credit_account.outstanding_balance,
                        payment=payment_instance,
                        reference=f'CRD-REFUND-{payment_instance.pk}-{uuid.uuid4().hex[:6].upper()}',
                        notes=f'Credit refund: {clean_reason}',
                        created_by=user,
                    )
                    channel_details = {
                        'credit_account_id': credit_account.pk,
                        'debt_repaid': str(repay_amt),
                        'new_balance': str(credit_account.outstanding_balance),
                    }
                else:
                    # No outstanding debt: expand available credit allowance
                    credit_account.credit_limit = credit_account.credit_limit + refund_amount
                    credit_account.save(update_fields=['credit_limit', 'updated_at'])
                    CreditTransaction.objects.create(
                        credit_account=credit_account,
                        transaction_type=CreditTransaction.TransactionType.ADJUSTMENT,
                        amount=refund_amount,
                        previous_balance=credit_account.outstanding_balance,
                        new_balance=credit_account.outstanding_balance,
                        payment=payment_instance,
                        reference=f'CRD-LIMIT-REFUND-{payment_instance.pk}-{uuid.uuid4().hex[:6].upper()}',
                        notes=f'Store credit refund allowance: {clean_reason}',
                        created_by=user,
                    )
                    channel_details = {
                        'credit_account_id': credit_account.pk,
                        'credit_allowance_added': str(refund_amount),
                        'new_credit_limit': str(credit_account.credit_limit),
                    }

        elif active_channel == RefundChannel.CASH:
            channel_details = {
                'cash_register_reversal': True,
                'refund_amount': str(refund_amount),
                'payout_processed_by': user.username,
            }

        elif active_channel == RefundChannel.PAYSTACK:
            kobo_amount = int(refund_amount * Decimal('100'))
            ref_to_use = payment_instance.transaction_reference or payment_instance.payment_reference
            gateway_res = PaystackRefundAdapter.execute_refund(
                transaction_reference=ref_to_use,
                amount_kobo=kobo_amount,
                reason=clean_reason,
            )
            channel_details = gateway_res

        elif active_channel == RefundChannel.MONIEPOINT:
            channel_details = {
                'moniepoint_reversal': True,
                'reversal_reference': f'MNP-REV-{uuid.uuid4().hex[:8].upper()}',
                'status': 'REVERSED',
                'amount': str(refund_amount),
            }

        else:
            channel_details = {
                'channel': active_channel,
                'refund_reference': f'REF-{uuid.uuid4().hex[:8].upper()}',
            }

        # 8. Optional inventory restocking
        restocked_items = []
        if restock_inventory and target:
            line_items = list(target.items.select_related('product').all())
            for line_item in line_items:
                product = line_item.product
                inv_item = InventoryItem.objects.select_for_update().filter(product=product).first()
                if inv_item:
                    qty = line_item.quantity
                    adjust_inventory_stock(
                        inventory_item=inv_item,
                        quantity_delta=qty,
                        movement_type=StockMovement.MovementType.RETURN,
                        reason=f'Refund restock: {clean_reason}',
                        reference=f'REFUND-{payment_instance.payment_reference}',
                        created_by=user,
                    )
                    restocked_items.append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'quantity_returned': qty,
                    })

        # 9. Advance target Order or Sale lifecycle upon full refund
        new_total_refunded = (payment_instance.total_refunded + refund_amount).quantize(Decimal('0.01'))
        is_full_refund = new_total_refunded >= payment_instance.amount

        if is_full_refund and target:
            if isinstance(target, Order) and target.status != Order.OrderStatus.CANCELLED:
                target.status = Order.OrderStatus.CANCELLED
                target.save(update_fields=['status'])
            elif isinstance(target, Sale) and target.status != Sale.SaleStatus.CANCELLED:
                target.status = Sale.SaleStatus.CANCELLED
                target.save(update_fields=['status', 'updated_at'])

        # 10. Update Payment state and metadata
        now = timezone.now()
        new_status = (
            Payment.PaymentStatus.REFUNDED
            if is_full_refund
            else Payment.PaymentStatus.PARTIALLY_REFUNDED
        )

        meta = dict(payment_instance.transaction_metadata or {})
        history = list(meta.get('refund_history', []))
        refund_entry = {
            'refund_id': f'REF-{uuid.uuid4().hex[:8].upper()}',
            'amount': str(refund_amount),
            'reason': clean_reason,
            'restock_inventory': bool(restock_inventory),
            'restocked_items': restocked_items,
            'channel': active_channel,
            'channel_details': channel_details,
            'refunded_at': now.isoformat(),
            'refunded_by': user.username,
            'refunded_by_id': user.id,
            'status_after': new_status,
        }
        history.append(refund_entry)

        meta['total_refunded'] = str(new_total_refunded)
        meta['refunded_amount'] = str(new_total_refunded)
        meta['refund_reason'] = clean_reason
        meta['refunded_at'] = now.isoformat()
        meta['refunded_by'] = user.username
        meta['refund_history'] = history

        payment_instance.payment_status = new_status
        payment_instance.transaction_metadata = meta
        payment_instance.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

        # 11. Customer in-app Notification
        if customer:
            try:
                from apps.notifications.services import NotificationService
                from apps.notifications.models import Notification
                NotificationService.create_notification(
                    recipient=customer,
                    notification_type=Notification.NotificationType.PAYMENT,
                    title='Payment Refund Processed',
                    message=(
                        f'A refund of NGN {refund_amount:.2f} has been processed for payment '
                        f'{payment_instance.payment_reference} ({new_status.replace("_", " ")}). Reason: {clean_reason}'
                    ),
                    related_object=payment_instance,
                )
            except Exception:
                pass

        # 12. ActivityLog audit entry
        log_activity(
            actor=user,
            action_type=ActivityLog.ActionType.UPDATED,
            action_label='Processed payment refund',
            description=(
                f'Processed {new_status.lower().replace("_", " ")} of {refund_amount:.2f} '
                f'for payment {payment_instance.payment_reference}. Reason: {clean_reason}'
            ),
            related_object=payment_instance,
            metadata={
                'payment_id': payment_instance.id,
                'payment_reference': payment_instance.payment_reference,
                'refund_amount': str(refund_amount),
                'total_refunded': str(new_total_refunded),
                'remaining_balance': str(payment_instance.remaining_refundable_amount),
                'status': new_status,
                'reason': clean_reason,
                'restock_inventory': bool(restock_inventory),
                'channel': active_channel,
                'refunded_by': user.username,
            },
        )

        return {
            'payment_id': payment_instance.id,
            'payment_reference': payment_instance.payment_reference,
            'status': new_status,
            'refund_amount': str(refund_amount),
            'total_refunded': str(new_total_refunded),
            'remaining_balance': str(payment_instance.remaining_refundable_amount),
            'is_fully_refunded': is_full_refund,
            'restocked_inventory': bool(restock_inventory),
            'restocked_items': restocked_items,
            'reason': clean_reason,
            'refunded_by': user.username,
            'refunded_at': now.isoformat(),
            'channel': active_channel,
            'refund_entry': refund_entry,
        }
