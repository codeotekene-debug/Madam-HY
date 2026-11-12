from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity

from .models import CreditAccount, CreditTransaction


class CreditService:
    """Centralized service for Credit account operations and POS sales enforcement."""

    @classmethod
    def get_credit_account(cls, customer):
        """Retrieve the CreditAccount for a customer or raise ValidationError."""
        if customer is None:
            raise ValidationError({'customer': 'Customer is required for credit.'})
        if getattr(customer, 'role', None) != 'CUSTOMER':
            raise ValidationError({'customer': 'Only users with role CUSTOMER can hold a credit account.'})
        try:
            return customer.credit_account
        except (CreditAccount.DoesNotExist, AttributeError):
            name = getattr(customer, 'get_full_name', lambda: '')() or getattr(customer, 'email', str(customer))
            raise ValidationError({'credit': f'Customer {name} does not have an active credit account.'})

    @classmethod
    def validate_credit_eligibility(cls, customer, amount):
        """
        Verify that the customer has an approved/active credit account with sufficient available credit.
        Raises ValidationError if ineligible.
        """
        account = cls.get_credit_account(customer)
        if amount is None or Decimal(str(amount)) <= Decimal('0.00'):
            raise ValidationError({'amount': 'Credit amount must be greater than zero.'})

        numeric_amount = Decimal(str(amount))
        available = account.get_available_credit()

        if not account.can_use_credit(numeric_amount):
            if account.status in {
                CreditAccount.Status.PENDING_APPROVAL,
                CreditAccount.Status.REJECTED,
                CreditAccount.Status.SUSPENDED,
                CreditAccount.Status.CLOSED,
            }:
                raise ValidationError({'credit': f'Credit account is {account.get_status_display().lower()} and not eligible for credit purchases.'})
            if not account.approved_by:
                raise ValidationError({'credit': 'Credit account has not been approved by an authorized manager.'})
            if available < numeric_amount:
                raise ValidationError({'credit': f'Insufficient available credit. Available credit: {available:.2f}, required: {numeric_amount:.2f}.'})
            raise ValidationError({'credit': 'Customer is not eligible to use credit for this amount.'})
        return account

    @classmethod
    @transaction.atomic
    def process_credit_sale(cls, sale, created_by=None):
        """
        Record a credit purchase for a completed POS Sale.
        Atomically updates CreditAccount balance and creates a CreditTransaction ledger entry.
        """
        if sale is None or sale.pk is None:
            raise ValidationError({'sale': 'An existing sale is required to process a credit purchase.'})
        if sale.customer is None:
            raise ValidationError({'customer': 'A customer is required for credit sales.'})

        account = cls.validate_credit_eligibility(sale.customer, sale.total)

        notes_detail = (
            f'Credit purchase for Order {sale.source_order.order_number}'
            if getattr(sale, 'source_order', None)
            else f'Credit purchase for POS sale {sale.sale_number}'
        )

        tx = account.record_credit_purchase(
            sale=sale,
            amount=sale.total,
            created_by=created_by,
            reference=f'CRD-SALE-{sale.sale_number}',
            notes=notes_detail,
        )
        return tx

    @classmethod
    @transaction.atomic
    def process_repayment(
        cls,
        credit_account,
        amount,
        payment_method,
        created_by,
        reference='',
        notes='',
        payment=None,
    ):
        """
        Record a customer credit repayment against an existing CreditAccount.
        Atomically updates CreditAccount balance, adjusts status, creates a CreditTransaction,
        and logs the audit activity.
        """
        if credit_account is None or credit_account.pk is None:
            raise ValidationError({'credit_account': 'A valid existing credit account is required.'})

        # Role permission enforcement
        allowed_roles = {'OWNER', 'MANAGER', 'CASHIER'}
        if not created_by or getattr(created_by, 'role', None) not in allowed_roles:
            raise ValidationError({'created_by': 'Only authorized staff (OWNER, MANAGER, CASHIER) can record repayments.'})

        # Validate amount
        if amount is None:
            raise ValidationError({'amount': 'Repayment amount is required.'})
        try:
            numeric_amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({'amount': 'Valid repayment amount is required.'})

        if numeric_amount <= Decimal('0.00'):
            raise ValidationError({'amount': 'Repayment amount must be strictly greater than zero.'})

        # Validate payment method
        if not payment_method or not str(payment_method).strip():
            raise ValidationError({'payment_method': 'Payment method is required.'})
        method_norm = str(payment_method).strip().upper()
        valid_methods = {'CASH', 'BANK_TRANSFER', 'TRANSFER', 'CARD', 'POS'}
        if method_norm not in valid_methods:
            raise ValidationError({
                'payment_method': f'Invalid payment method "{payment_method}". Accepted methods: CASH, BANK_TRANSFER, CARD, POS, TRANSFER.'
            })
        if method_norm == 'TRANSFER':
            method_norm = 'BANK_TRANSFER'
        elif method_norm == 'POS':
            method_norm = 'CARD'

        # Row-level locking and transaction
        account = CreditAccount.objects.select_for_update().get(pk=credit_account.pk)

        if numeric_amount > account.outstanding_balance:
            raise ValidationError({
                'amount': f'Repayment amount ({numeric_amount:.2f}) cannot exceed current outstanding balance ({account.outstanding_balance:.2f}).'
            })

        ref_text = reference.strip() if reference else ''
        notes_text = notes.strip() if notes else ''
        method_note = f'Payment method: {method_norm}'
        combined_notes = f'{method_note}. {notes_text}'.strip() if notes_text else method_note

        tx = account.record_repayment(
            amount=numeric_amount,
            payment=payment,
            created_by=created_by,
            reference=ref_text,
            notes=combined_notes,
        )

        customer = account.customer
        customer_display = getattr(customer, 'get_full_name', lambda: '')() or customer.username
        log_activity(
            actor=created_by,
            action_type=ActivityLog.ActionType.PAYMENT,
            action_label='Credit repayment recorded',
            description=(
                f'Recorded repayment of {numeric_amount:.2f} via {method_norm} for customer '
                f'{customer_display} ({customer.email}). Outstanding balance reduced from '
                f'{tx.previous_balance:.2f} to {tx.new_balance:.2f}.'
            ),
            related_object=account,
            metadata={
                'credit_account_id': account.pk,
                'customer_id': customer.pk,
                'customer_email': customer.email,
                'repayment_amount': str(numeric_amount),
                'payment_method': method_norm,
                'previous_balance': str(tx.previous_balance),
                'new_balance': str(tx.new_balance),
                'transaction_id': tx.pk,
                'transaction_reference': tx.reference,
                'payment_id': payment.pk if payment else None,
            },
        )

        return tx, account
