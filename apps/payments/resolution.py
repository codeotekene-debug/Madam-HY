import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.credits.models import CreditAccount, CreditTransaction
from apps.orders.models import Order
from apps.sales.models import Sale

from .models import Payment
from .reconciliation import ReconciliationClassification, ReconciliationService
from .services import PaymentService


class ResolutionStrategy:
    CREDIT_CUSTOMER = 'CREDIT_CUSTOMER'
    RECORD_COMPLEMENTARY_PAYMENT = 'RECORD_COMPLEMENTARY_PAYMENT'
    MANUAL_OVERRIDE = 'MANUAL_OVERRIDE'

    CHOICES = (CREDIT_CUSTOMER, RECORD_COMPLEMENTARY_PAYMENT, MANUAL_OVERRIDE)


class PaymentResolutionService:
    """
    Centralized service for managing and resolving financial discrepancies,
    overpayments, partial payments, and gateway mismatches.
    """

    ALLOWED_ROLES = ('OWNER', 'MANAGER')

    @classmethod
    def validate_actor(cls, actor):
        if not actor or not getattr(actor, 'is_authenticated', False):
            raise ValidationError({'actor': 'Authentication required for resolution.'})
        if getattr(actor, 'role', None) not in cls.ALLOWED_ROLES:
            raise ValidationError({'actor': 'Only owners and managers can resolve financial discrepancies.'})

    @classmethod
    def list_discrepancies(cls, classification=None, is_resolved=None):
        """
        Gathers transactions and payments exhibiting discrepancies or mismatches.
        Filterable by classification ('PARTIALLY_PAID', 'OVERPAID', 'MISMATCH')
        and resolution state.
        """
        records = []
        seen_targets = set()

        # 1. Inspect payments with recorded mismatch flags
        mismatched_payments = Payment.objects.filter(
            Q(transaction_metadata__webhook_verification_status='MISMATCH')
            | Q(transaction_metadata__verification_status='MISMATCH')
            | Q(transaction_metadata__webhook_discrepancy__isnull=False)
            | Q(transaction_metadata__has_discrepancy=True)
            | Q(payment_status=Payment.PaymentStatus.FAILED)
        ).select_related('sale', 'order', 'customer')

        for p in mismatched_payments:
            target = p.sale or p.order
            target_key = f"{'sale' if p.sale else 'order'}-{target.pk if target else 'none'}-{p.pk}"
            seen_targets.add(target_key)

            meta = p.transaction_metadata or {}
            resolved = meta.get('resolution_status') == 'RESOLVED'

            if is_resolved is not None and resolved != is_resolved:
                continue

            target_type = 'sale' if p.sale else ('order' if p.order else 'standalone')
            target_id = target.pk if target else None
            identifier = (
                target.sale_number
                if p.sale
                else (target.order_number if p.order else p.payment_reference)
            )
            target_total = target.total if target else p.amount

            discrepancy_msg = (
                meta.get('webhook_discrepancy')
                or meta.get('discrepancy')
                or meta.get('notes')
                or f'Payment status: {p.payment_status}'
            )

            records.append({
                'payment_id': p.id,
                'payment_reference': p.payment_reference,
                'transaction_reference': p.transaction_reference,
                'target_type': target_type,
                'target_id': target_id,
                'target_identifier': identifier,
                'amount': f'{p.amount:.2f}',
                'target_total': f'{target_total:.2f}',
                'classification': 'MISMATCH',
                'status': p.payment_status,
                'discrepancy_details': discrepancy_msg,
                'is_resolved': resolved,
                'resolution': {
                    'action': meta.get('resolution_action'),
                    'notes': meta.get('resolution_notes'),
                    'resolved_at': meta.get('resolved_at'),
                    'resolved_by': meta.get('resolved_by_username'),
                } if resolved else None,
            })

        # 2. Inspect Sales and Orders for financial imbalances via ReconciliationService
        for sale in Sale.objects.exclude(status=Sale.SaleStatus.CANCELLED).select_related('customer')[:50]:
            bal = PaymentService.get_transaction_balance(sale)
            completed_amt = bal['completed_amount']
            total = bal['transaction_total']

            class_val = None
            if completed_amt > total:
                class_val = ReconciliationClassification.OVERPAID.value
            elif 0 < completed_amt < total:
                class_val = ReconciliationClassification.PARTIALLY_PAID.value

            if class_val:
                key = f'sale-{sale.pk}'
                latest_payment = sale.payments.order_by('-created_at').first()
                p_id = latest_payment.id if latest_payment else None
                meta = latest_payment.transaction_metadata if latest_payment else {}
                resolved = meta.get('resolution_status') == 'RESOLVED'

                if is_resolved is not None and resolved != is_resolved:
                    continue

                records.append({
                    'payment_id': p_id,
                    'payment_reference': latest_payment.payment_reference if latest_payment else f'SALE-{sale.sale_number}',
                    'transaction_reference': latest_payment.transaction_reference if latest_payment else '',
                    'target_type': 'sale',
                    'target_id': sale.id,
                    'target_identifier': sale.sale_number,
                    'amount': f'{completed_amt:.2f}',
                    'target_total': f'{total:.2f}',
                    'outstanding_amount': f'{bal["outstanding_amount"]:.2f}',
                    'overpaid_amount': f'{bal["overpaid_amount"]:.2f}',
                    'classification': class_val,
                    'status': sale.payment_status,
                    'discrepancy_details': f'Completed payments ({completed_amt:.2f}) do not match sale total ({total:.2f}).',
                    'is_resolved': resolved,
                    'resolution': {
                        'action': meta.get('resolution_action'),
                        'notes': meta.get('resolution_notes'),
                        'resolved_at': meta.get('resolved_at'),
                        'resolved_by': meta.get('resolved_by_username'),
                    } if resolved else None,
                })

        for order in Order.objects.exclude(status=Order.OrderStatus.CANCELLED).select_related('customer')[:50]:
            bal = PaymentService.get_transaction_balance(order)
            completed_amt = bal['completed_amount']
            total = bal['transaction_total']

            class_val = None
            if completed_amt > total:
                class_val = ReconciliationClassification.OVERPAID.value
            elif 0 < completed_amt < total:
                class_val = ReconciliationClassification.PARTIALLY_PAID.value

            if class_val:
                latest_payment = order.payments.order_by('-created_at').first()
                p_id = latest_payment.id if latest_payment else None
                meta = latest_payment.transaction_metadata if latest_payment else {}
                resolved = meta.get('resolution_status') == 'RESOLVED'

                if is_resolved is not None and resolved != is_resolved:
                    continue

                records.append({
                    'payment_id': p_id,
                    'payment_reference': latest_payment.payment_reference if latest_payment else f'ORD-{order.order_number}',
                    'transaction_reference': latest_payment.transaction_reference if latest_payment else '',
                    'target_type': 'order',
                    'target_id': order.id,
                    'target_identifier': order.order_number,
                    'amount': f'{completed_amt:.2f}',
                    'target_total': f'{total:.2f}',
                    'outstanding_amount': f'{bal["outstanding_amount"]:.2f}',
                    'overpaid_amount': f'{bal["overpaid_amount"]:.2f}',
                    'classification': class_val,
                    'status': order.payment_status,
                    'discrepancy_details': f'Completed payments ({completed_amt:.2f}) do not match order total ({total:.2f}).',
                    'is_resolved': resolved,
                    'resolution': {
                        'action': meta.get('resolution_action'),
                        'notes': meta.get('resolution_notes'),
                        'resolved_at': meta.get('resolved_at'),
                        'resolved_by': meta.get('resolved_by_username'),
                    } if resolved else None,
                })

        if classification:
            clean_class = str(classification).strip().upper()
            records = [r for r in records if r['classification'] == clean_class]

        return records

    @classmethod
    @transaction.atomic
    def resolve_discrepancy(
        cls,
        payment_id_or_ref,
        strategy: str,
        actor,
        resolution_notes: str,
        amount=None,
        payment_method=None,
        mark_completed: bool = False,
    ) -> dict:
        """
        Executes a resolution action for a financial discrepancy with row-level locks,
        idempotency checks, and audit logging.
        """
        cls.validate_actor(actor)

        clean_notes = str(resolution_notes or '').strip()
        if not clean_notes or len(clean_notes) < 5:
            raise ValidationError({
                'resolution_notes': 'Detailed resolution notes (minimum 5 characters) are required.'
            })

        norm_strategy = str(strategy or '').strip().upper()
        if norm_strategy not in ResolutionStrategy.CHOICES:
            raise ValidationError({
                'strategy': f'Invalid resolution strategy "{strategy}". Allowed: {", ".join(ResolutionStrategy.CHOICES)}.'
            })

        clean_id = str(payment_id_or_ref).strip()
        payment = None

        # Resolve Payment instance with row-level lock
        try:
            payment = Payment.objects.select_for_update().get(pk=int(clean_id))
        except (Payment.DoesNotExist, ValueError):
            payment = Payment.objects.select_for_update().filter(
                Q(payment_reference=clean_id) | Q(transaction_reference=clean_id)
            ).first()

        if not payment:
            # Fallback: check if target Sale or Order was passed
            sale = None
            order = None
            try:
                sale = Sale.objects.select_for_update().get(pk=int(clean_id))
            except (Sale.DoesNotExist, ValueError):
                pass
            if not sale:
                try:
                    order = Order.objects.select_for_update().get(pk=int(clean_id))
                except (Order.DoesNotExist, ValueError):
                    pass

            target = sale or order
            if target:
                payment = target.payments.select_for_update().order_by('-created_at').first()

        if not payment:
            raise ValidationError({'payment': f'Payment reference or transaction "{clean_id}" not found.'})

        # Double-resolution guard
        meta = dict(payment.transaction_metadata or {})
        if meta.get('resolution_status') == 'RESOLVED':
            raise ValidationError({
                'resolution': f'Payment {payment.payment_reference} has already been resolved by {meta.get("resolved_by_username", "management")}.'
            })

        target = payment.sale or payment.order
        customer = payment.customer or (target.customer if target else None)
        resolution_payload = {}

        # ----------------------------------------------------------------------
        # Strategy 1: CREDIT_CUSTOMER (Excess / Overpayment transfer)
        # ----------------------------------------------------------------------
        if norm_strategy == ResolutionStrategy.CREDIT_CUSTOMER:
            if not customer:
                raise ValidationError({
                    'customer': 'A customer is required to apply store credit for an overpayment.'
                })

            # Calculate excess amount
            if amount is not None:
                try:
                    excess_amt = Decimal(str(amount)).quantize(Decimal('0.01'))
                except (InvalidOperation, TypeError, ValueError):
                    raise ValidationError({'amount': 'A valid monetary excess amount is required.'})
            else:
                if target:
                    bal = PaymentService.get_transaction_balance(target)
                    excess_amt = bal['overpaid_amount']
                else:
                    excess_amt = Decimal('0.00')

            if excess_amt <= Decimal('0.00'):
                raise ValidationError({
                    'amount': 'Excess amount to credit customer must be greater than zero.'
                })

            # Fetch or initialize CustomerCreditAccount
            account = CreditAccount.objects.select_for_update().filter(customer=customer).first()
            if not account:
                account = CreditAccount.objects.create(
                    customer=customer,
                    credit_limit=excess_amt,
                    outstanding_balance=Decimal('0.00'),
                    status=CreditAccount.Status.APPROVED,
                    approved_by=actor,
                    approved_at=timezone.now(),
                    notes='Auto-initialized store credit account for overpayment resolution.',
                )
                applied_repayment = Decimal('0.00')
                applied_credit = excess_amt
            else:
                # If account has debt, pay down debt; otherwise, increase available credit
                if account.outstanding_balance > 0:
                    repay_amt = min(excess_amt, account.outstanding_balance)
                    account.record_repayment(
                        amount=repay_amt,
                        payment=payment,
                        created_by=actor,
                        reference=f'CRD-RES-{payment.pk}',
                        notes=f'Overpayment refund repayment: {clean_notes}',
                    )
                    applied_repayment = repay_amt
                    applied_credit = excess_amt - repay_amt
                    if applied_credit > 0:
                        account.credit_limit = account.credit_limit + applied_credit
                        account.save(update_fields=['credit_limit', 'updated_at'])
                else:
                    applied_repayment = Decimal('0.00')
                    applied_credit = excess_amt
                    account.credit_limit = account.credit_limit + applied_credit
                    if account.status == CreditAccount.Status.PENDING_APPROVAL:
                        account.status = CreditAccount.Status.APPROVED
                        account.approved_by = actor
                        account.approved_at = timezone.now()
                    account.save(update_fields=['credit_limit', 'status', 'approved_by', 'approved_at', 'updated_at'])

            # Record ledger audit entry
            CreditTransaction.objects.create(
                credit_account=account,
                transaction_type=CreditTransaction.TransactionType.ADJUSTMENT,
                amount=excess_amt,
                previous_balance=account.outstanding_balance,
                new_balance=account.outstanding_balance,
                payment=payment,
                reference=f'CRD-RESOLVE-{payment.pk}',
                notes=f'Overpayment discrepancy credited: {clean_notes}',
                created_by=actor,
            )

            resolution_payload = {
                'credited_amount': str(excess_amt),
                'repaid_debt': str(applied_repayment),
                'credit_allowance_added': str(applied_credit),
                'credit_account_id': account.pk,
            }

        # ----------------------------------------------------------------------
        # Strategy 2: RECORD_COMPLEMENTARY_PAYMENT (Partial payment balance clear)
        # ----------------------------------------------------------------------
        elif norm_strategy == ResolutionStrategy.RECORD_COMPLEMENTARY_PAYMENT:
            if not target:
                raise ValidationError({
                    'transaction': 'A linked Sale or Order is required to record a complementary payment.'
                })

            bal = PaymentService.get_transaction_balance(target)
            outstanding = bal['outstanding_amount']

            if amount is not None:
                try:
                    comp_amt = Decimal(str(amount)).quantize(Decimal('0.01'))
                except (InvalidOperation, TypeError, ValueError):
                    raise ValidationError({'amount': 'A valid monetary payment amount is required.'})
            else:
                comp_amt = outstanding

            if comp_amt <= Decimal('0.00'):
                raise ValidationError({'amount': 'Complementary payment amount must be greater than zero.'})

            comp_method = payment_method or Payment.PaymentMethod.CASH
            short_id = uuid.uuid4().hex[:8].upper()
            target_code = 'SALE' if isinstance(target, Sale) else 'ORD'
            comp_ref = f'PAY-COMP-{target_code}-{target.pk}-{short_id}'

            comp_payment = PaymentService.create_payment(
                payment_reference=comp_ref,
                sale=target if isinstance(target, Sale) else None,
                order=target if isinstance(target, Order) else None,
                customer=customer,
                cashier=actor,
                amount=comp_amt,
                payment_method=comp_method,
                payment_status=Payment.PaymentStatus.COMPLETED,
                transaction_reference=f'TXN-COMP-{short_id}',
                notes=f'Complementary balance payment: {clean_notes}',
                allow_completed=True,
            )

            # Advance target if fully cleared
            new_bal = PaymentService.get_transaction_balance(target)
            if new_bal['outstanding_amount'] == Decimal('0.00'):
                if isinstance(target, Sale) and target.payment_status != Sale.PaymentStatus.COMPLETED:
                    target.payment_status = Sale.PaymentStatus.COMPLETED
                    target.save(update_fields=['payment_status'])
                elif isinstance(target, Order) and target.payment_status != Order.PaymentStatus.CONFIRMED:
                    target.payment_status = Order.PaymentStatus.CONFIRMED
                    target.save(update_fields=['payment_status'])

            resolution_payload = {
                'complementary_payment_id': comp_payment.id,
                'complementary_payment_reference': comp_payment.payment_reference,
                'complementary_amount': str(comp_amt),
                'remaining_outstanding': str(new_bal['outstanding_amount']),
            }

        # ----------------------------------------------------------------------
        # Strategy 3: MANUAL_OVERRIDE (Administrative justification)
        # ----------------------------------------------------------------------
        elif norm_strategy == ResolutionStrategy.MANUAL_OVERRIDE:
            if mark_completed and payment.payment_status == Payment.PaymentStatus.PENDING:
                payment.payment_status = Payment.PaymentStatus.COMPLETED

            resolution_payload = {
                'manual_override': True,
                'mark_completed': mark_completed,
            }

        # Update Payment metadata with resolution state
        now = timezone.now()
        meta['resolution_status'] = 'RESOLVED'
        meta['resolution_action'] = norm_strategy
        meta['resolved_at'] = now.isoformat()
        meta['resolved_by_id'] = actor.id
        meta['resolved_by_username'] = actor.username
        meta['resolution_notes'] = clean_notes
        meta['resolution_payload'] = resolution_payload

        # Clean up discrepancy flags
        if 'webhook_verification_status' in meta and meta['webhook_verification_status'] == 'MISMATCH':
            meta['webhook_verification_status'] = 'RESOLVED'
        if 'verification_status' in meta and meta['verification_status'] == 'MISMATCH':
            meta['verification_status'] = 'RESOLVED'

        payment.transaction_metadata = meta
        payment.save(update_fields=['payment_status', 'transaction_metadata', 'updated_at'])

        # Send in-app notification if customer exists
        try:
            from apps.notifications.services import NotificationService
            from apps.notifications.models import Notification
            if customer:
                NotificationService.create_notification(
                    recipient=customer,
                    notification_type=Notification.NotificationType.PAYMENT,
                    title='Payment Discrepancy Resolved',
                    message=(
                        f'Management has resolved the discrepancy on payment {payment.payment_reference} '
                        f'({norm_strategy.replace("_", " ")}): {clean_notes}'
                    ),
                    related_object=payment,
                )
        except Exception:
            pass

        # Log Activity audit
        log_activity(
            actor=actor,
            action_type=ActivityLog.ActionType.UPDATED,
            action_label='Resolved payment discrepancy',
            description=(
                f'Resolved discrepancy for payment {payment.payment_reference} '
                f'via {norm_strategy}: {clean_notes}'
            ),
            related_object=payment,
            metadata={
                'payment_id': payment.id,
                'payment_reference': payment.payment_reference,
                'strategy': norm_strategy,
                'resolution_notes': clean_notes,
                'resolved_by': actor.username,
                'resolution_payload': resolution_payload,
            },
        )

        return {
            'payment_id': payment.id,
            'payment_reference': payment.payment_reference,
            'status': 'RESOLVED',
            'strategy': norm_strategy,
            'resolution_notes': clean_notes,
            'resolved_by': actor.username,
            'resolved_at': now.isoformat(),
            'details': resolution_payload,
        }
