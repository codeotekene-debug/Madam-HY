from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


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
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_expenses',
        help_text='User who recorded the expense. Must reference an existing user.',
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

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Historical expense records must be preserved. They cannot be casually deleted.')

    @property
    def amount_display(self):
        return self.amount.quantize(Decimal('0.01'))
