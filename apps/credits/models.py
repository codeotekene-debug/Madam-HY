from decimal import Decimal
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class CreditAccount(models.Model):
    """Customer credit allowance and outstanding account balance."""

    class Status(models.TextChoices):
        PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        ACTIVE = 'ACTIVE', 'Active'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
        DUE = 'DUE', 'Due'
        OVERDUE = 'OVERDUE', 'Overdue'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        CLOSED = 'CLOSED', 'Closed'
        REJECTED = 'REJECTED', 'Rejected'

    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='credit_account',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text='Customer assigned to this credit account.',
    )
    credit_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Maximum credit allowed for this customer.',
    )
    outstanding_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Current unpaid credit balance on this account.',
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
        help_text='Current lifecycle state of the credit account.',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_credit_accounts',
        help_text='Owner or manager who approved the credit allowance.',
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the credit allowance was approved.',
    )
    next_due_date = models.DateField(
        null=True,
        blank=True,
        help_text='Next scheduled repayment due date.',
    )
    last_payment_date = models.DateField(
        null=True,
        blank=True,
        help_text='Most recent payment date on the account.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Operational notes about the customer account.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Credit Account'
        verbose_name_plural = 'Credit Accounts'
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['approved_by']),
            models.Index(fields=['next_due_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(credit_limit__gte=0),
                name='credit_account_credit_limit_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(outstanding_balance__gte=0),
                name='credit_account_outstanding_balance_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.customer.get_full_name() or self.customer.email} - {self.get_status_display()}"

    def clean(self):
        super().clean()

        if self.customer and self.customer.role != 'CUSTOMER':
            raise ValidationError({'customer': 'Only CUSTOMER role users can have a credit account.'})

        if self.credit_limit < 0:
            raise ValidationError({'credit_limit': 'Credit limit cannot be negative.'})
        if self.outstanding_balance < 0:
            raise ValidationError({'outstanding_balance': 'Outstanding balance cannot be negative.'})

        allowed_approvers = {'OWNER', 'MANAGER'}
        if self.status in {self.Status.APPROVED, self.Status.ACTIVE, self.Status.PARTIALLY_PAID, self.Status.DUE, self.Status.OVERDUE, self.Status.SUSPENDED, self.Status.CLOSED}:
            if not self.approved_by:
                raise ValidationError({'approved_by': 'Approved credit accounts must have an authorized approver.'})
            if self.approved_by.role not in allowed_approvers:
                raise ValidationError({'approved_by': 'Only OWNER or MANAGER can approve a credit account.'})

        if self.approved_by and self.approved_by.role not in allowed_approvers:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can approve a credit account.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.outstanding_balance > 0 or self.transactions.exists():
            raise ValidationError('Historical credit account records must be preserved. They cannot be casually deleted.')
        return super().delete(*args, **kwargs)

    def get_available_credit(self):
        return max(self.credit_limit - self.outstanding_balance, Decimal('0.00'))

    def can_use_credit(self, amount):
        if amount is None:
            return False
        amount = Decimal(str(amount))
        if amount <= 0:
            return False
        if self.customer.role != 'CUSTOMER':
            return False
        if self.status in {self.Status.PENDING_APPROVAL, self.Status.REJECTED, self.Status.SUSPENDED, self.Status.CLOSED}:
            return False
        if self.status in {self.Status.APPROVED, self.Status.ACTIVE, self.Status.PARTIALLY_PAID, self.Status.DUE, self.Status.OVERDUE}:
            if not self.approved_by:
                return False
            return self.get_available_credit() >= amount
        return False

    def get_status_for_balance(self):
        if self.status in {self.Status.PENDING_APPROVAL, self.Status.REJECTED, self.Status.CLOSED, self.Status.SUSPENDED}:
            return self.status
        if self.is_overdue():
            return self.Status.OVERDUE
        if self.outstanding_balance == 0:
            return self.Status.APPROVED if self.status in {self.Status.APPROVED, self.Status.ACTIVE} else self.status
        if self.outstanding_balance < self.credit_limit:
            return self.Status.PARTIALLY_PAID
        return self.Status.ACTIVE

    def is_overdue(self):
        if self.outstanding_balance <= 0 or not self.next_due_date:
            return False
        return date.today() > self.next_due_date

    @transaction.atomic
    def record_credit_purchase(self, sale, amount, created_by=None, reference='', notes='', validate_only=False):
        if amount is None:
            raise ValidationError({'amount': 'Credit purchase amount is required.'})
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError({'amount': 'Credit purchase amount must be greater than zero.'})
        if sale is None:
            raise ValidationError({'sale': 'A credit purchase must reference a Sale.'})
        if sale.customer_id != self.customer_id:
            raise ValidationError({'sale': 'The sale customer must match the credit account customer.'})
        if not self.can_use_credit(amount):
            raise ValidationError({'amount': 'Customer cannot use this amount of credit on the current account.'})

        account = CreditAccount.objects.select_for_update().get(pk=self.pk)
        if not account.can_use_credit(amount):
            raise ValidationError({'amount': 'Customer cannot use this amount of credit on the current account.'})

        previous_balance = account.outstanding_balance
        new_balance = previous_balance + amount
        if new_balance > account.credit_limit:
            raise ValidationError({'amount': 'This credit purchase would exceed the approved credit limit.'})

        account.outstanding_balance = new_balance
        if account.status == account.Status.APPROVED:
            account.status = account.Status.ACTIVE
        if account.status not in {account.Status.ACTIVE, account.Status.PARTIALLY_PAID, account.Status.DUE, account.Status.OVERDUE}:
            raise ValidationError({'status': 'This credit account is not eligible for a new purchase.'})
        account.save(update_fields=['outstanding_balance', 'status', 'updated_at'])

        self.outstanding_balance = account.outstanding_balance
        self.status = account.status

        tx = CreditTransaction.objects.create(
            credit_account=account,
            transaction_type=CreditTransaction.TransactionType.CREDIT_PURCHASE,
            amount=amount,
            previous_balance=previous_balance,
            new_balance=new_balance,
            sale=sale,
            reference=reference or f'CRD-PURCHASE-{account.pk}-{account.transactions.count() + 1}',
            notes=notes,
            created_by=created_by,
        )

        if validate_only:
            return tx
        return tx

    @transaction.atomic
    def record_repayment(self, amount, payment=None, created_by=None, reference='', notes=''):
        if amount is None:
            raise ValidationError({'amount': 'Repayment amount is required.'})
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError({'amount': 'Repayment amount must be greater than zero.'})

        account = CreditAccount.objects.select_for_update().get(pk=self.pk)
        if account.outstanding_balance < amount:
            raise ValidationError({'amount': 'Repayment cannot exceed the current outstanding balance.'})

        previous_balance = account.outstanding_balance
        new_balance = previous_balance - amount
        if new_balance < 0:
            raise ValidationError({'amount': 'Repayment would create a negative balance.'})

        account.outstanding_balance = new_balance
        if amount > 0:
            account.last_payment_date = date.today()
        if account.outstanding_balance == 0:
            account.status = account.Status.APPROVED
        elif account.status == account.Status.APPROVED:
            account.status = account.Status.PARTIALLY_PAID
        account.save(update_fields=['outstanding_balance', 'status', 'last_payment_date', 'updated_at'])

        self.outstanding_balance = account.outstanding_balance
        self.status = account.status
        self.last_payment_date = account.last_payment_date

        tx = CreditTransaction.objects.create(
            credit_account=account,
            transaction_type=CreditTransaction.TransactionType.REPAYMENT,
            amount=amount,
            previous_balance=previous_balance,
            new_balance=new_balance,
            payment=payment,
            reference=reference or f'CRD-REPAY-{account.pk}-{account.transactions.count() + 1}',
            notes=notes,
            created_by=created_by,
        )
        return tx


class CreditTransaction(models.Model):
    """Immutable ledger for all credit-related balance movements."""

    class TransactionType(models.TextChoices):
        CREDIT_ISSUED = 'CREDIT_ISSUED', 'Credit Issued'
        CREDIT_PURCHASE = 'CREDIT_PURCHASE', 'Credit Purchase'
        REPAYMENT = 'REPAYMENT', 'Repayment'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        LATE_FEE = 'LATE_FEE', 'Late Fee'
        WRITE_OFF = 'WRITE_OFF', 'Write Off'
        REVERSAL = 'REVERSAL', 'Reversal'

    credit_account = models.ForeignKey(
        CreditAccount,
        on_delete=models.PROTECT,
        related_name='transactions',
        help_text='Credit account affected by this ledger entry.',
    )
    transaction_type = models.CharField(
        max_length=25,
        choices=TransactionType.choices,
        help_text='Type of credit ledger movement.',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Monetary change for this ledger entry.',
    )
    previous_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Outstanding balance before this transaction.',
    )
    new_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Outstanding balance after this transaction.',
    )
    sale = models.ForeignKey(
        'sales.Sale',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='credit_transactions',
        help_text='Sale associated with a credit purchase entry.',
    )
    payment = models.ForeignKey(
        'payments.Payment',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='credit_transactions',
        help_text='Payment associated with a repayment or settlement entry.',
    )
    reference = models.CharField(
        max_length=120,
        blank=True,
        help_text='External or internal reference for this ledger entry.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Notes about the ledger entry.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='credit_transactions',
        help_text='Staff or owner who recorded the ledger entry.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Credit Transaction'
        verbose_name_plural = 'Credit Transactions'
        indexes = [
            models.Index(fields=['credit_account', '-created_at']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['sale']),
            models.Index(fields=['payment']),
            models.Index(fields=['reference']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='credit_transaction_amount_positive',
            ),
            models.CheckConstraint(
                check=models.Q(previous_balance__gte=0),
                name='credit_transaction_previous_balance_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(new_balance__gte=0),
                name='credit_transaction_new_balance_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.credit_account} - {self.get_transaction_type_display()}"

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError({'amount': 'Transaction amount must be greater than zero.'})
        if self.previous_balance < 0:
            raise ValidationError({'previous_balance': 'Previous balance cannot be negative.'})
        if self.new_balance < 0:
            raise ValidationError({'new_balance': 'New balance cannot be negative.'})

        if self.transaction_type == self.TransactionType.CREDIT_PURCHASE and not self.sale:
            raise ValidationError({'sale': 'Credit purchase transactions must reference a Sale.'})
        if self.transaction_type == self.TransactionType.REPAYMENT and self.payment is not None and self.payment.customer_id != self.credit_account.customer_id:
            raise ValidationError({'payment': 'Repayment payment must belong to the same customer account.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Historical credit ledger entries are protected and cannot be deleted.')
