from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Expense(models.Model):
    """Business expense record owned by the Expenses domain."""

    class Category(models.TextChoices):
        RENT = 'RENT', 'Rent'
        UTILITIES = 'UTILITIES', 'Utilities'
        SUPPLIES = 'SUPPLIES', 'Supplies'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        TRANSPORT = 'TRANSPORT', 'Transport'
        SALARIES = 'SALARIES', 'Salaries'
        MARKETING = 'MARKETING', 'Marketing'
        OTHER = 'OTHER', 'Other'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CARD = 'CARD', 'Card'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text='Unique UUID identifier for public and API routing.',
    )
    expense_reference = models.CharField(
        max_length=80,
        unique=True,
        db_index=True,
        help_text='Unique expense reference or receipt identifier.',
    )
    category = models.CharField(
        max_length=25,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
        help_text='Classification of the expense for reporting and analysis.',
    )
    description = models.TextField(
        blank=True,
        help_text='Detailed description of the expense.',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount spent by the business.',
    )
    expense_date = models.DateField(
        db_index=True,
        help_text='Date the expense was incurred.',
    )
    vendor = models.CharField(
        max_length=200,
        help_text='Vendor or payee name for the expense.',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        help_text='How the expense was paid.',
    )
    payment_reference = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text='Optional invoice, receipt, or payment reference.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text='Approval status of the expense record.',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_expenses',
        help_text='User who recorded the expense. Must reference an existing user.',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_expenses',
        help_text='Manager or owner who approved or rejected the expense.',
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the expense was approved or rejected.',
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text='Reason for rejecting the expense, if applicable.',
    )
    receipt_image = models.ImageField(
        upload_to='expenses/receipts/',
        null=True,
        blank=True,
        help_text='Receipt or invoice image attachment.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Additional notes for audit and follow-up.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'
        indexes = [
            models.Index(fields=['category', '-expense_date']),
            models.Index(fields=['payment_method', '-expense_date']),
            models.Index(fields=['recorded_by', '-expense_date']),
            models.Index(fields=['status', '-expense_date']),
            models.Index(fields=['vendor']),
            models.Index(fields=['-created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['expense_reference'],
                name='expense_reference_unique',
            ),
            models.CheckConstraint(
                check=models.Q(amount__gt=Decimal('0.00')),
                name='expense_amount_positive',
            ),
            models.CheckConstraint(
                check=models.Q(expense_date__isnull=False),
                name='expense_date_required',
            ),
        ]

    def __str__(self):
        return f'{self.expense_reference} - {self.vendor} ({self.amount})'

    def clean(self):
        super().clean()

        if self.amount is None or self.amount <= Decimal('0.00'):
            raise ValidationError({'amount': 'Expense amount must be greater than zero.'})

        if not self.expense_date:
            raise ValidationError({'expense_date': 'Expense date is required.'})

        if not self.vendor:
            raise ValidationError({'vendor': 'Vendor or payee is required.'})

        if self.recorded_by_id is None:
            raise ValidationError({'recorded_by': 'A user must be assigned to record the expense.'})

        if self.recorded_by and self.recorded_by.role not in {'OWNER', 'MANAGER', 'CASHIER', 'STAFF'}:
            raise ValidationError({'recorded_by': 'Only staff or owner roles can record expenses.'})

        if self.approved_by and self.approved_by.role not in {'OWNER', 'MANAGER'}:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can approve or reject expenses.'})

        # Prevent modifying approved expenses
        if self.pk:
            try:
                orig = Expense.objects.get(pk=self.pk)
                if orig.status == self.Status.APPROVED:
                    immutable_fields = [
                        'amount', 'category', 'expense_date', 'vendor',
                        'payment_method', 'expense_reference', 'recorded_by_id',
                        'status',
                    ]
                    for field in immutable_fields:
                        if getattr(orig, field) != getattr(self, field):
                            raise ValidationError({
                                field: f'Approved expenses cannot be modified. Field {field} is immutable.'
                            })
            except Expense.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Historical expense records must be preserved. They cannot be casually deleted.')

    @property
    def amount_display(self):
        return self.amount.quantize(Decimal('0.01'))

    def approve(self, user):
        """Approve the expense record."""
        if not user or user.role not in {'OWNER', 'MANAGER'}:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can approve expenses.'})
        if self.status == self.Status.APPROVED:
            raise ValidationError({'status': 'Expense is already approved.'})
        if self.status == self.Status.REJECTED:
            raise ValidationError({'status': 'Rejected expenses cannot be approved.'})

        self.status = self.Status.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    def reject(self, user, reason=''):
        """Reject the expense record."""
        if not user or user.role not in {'OWNER', 'MANAGER'}:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can reject expenses.'})
        if self.status == self.Status.APPROVED:
            raise ValidationError({'status': 'Approved expenses cannot be rejected.'})
        if self.status == self.Status.REJECTED:
            raise ValidationError({'status': 'Expense is already rejected.'})

        self.status = self.Status.REJECTED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejection_reason = (reason or '').strip()
        self.save()
