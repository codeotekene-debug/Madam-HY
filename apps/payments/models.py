from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Payment(models.Model):
    """Payment record for a Sale or Order transaction without owning inventory or credit accounting."""

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CARD = 'CARD', 'Card'
        CREDIT = 'CREDIT', 'Credit'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'

    payment_reference = models.CharField(
        max_length=80,
        unique=True,
        help_text='Unique payment reference or transaction identifier.',
    )
    sale = models.ForeignKey(
        'sales.Sale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text='Related POS sale when payment belongs to a sale.',
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text='Related customer order when payment belongs to an order.',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_payments',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text='Customer involved in the payment context.',
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payments',
        help_text='Staff member who recorded or processed the payment.',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Actual monetary payment amount recorded for this transaction.',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        help_text='Payment method used for this transaction.',
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        help_text='Current payment state. Does not manage credit or balance accounting.',
    )
    transaction_reference = models.CharField(
        max_length=120,
        blank=True,
        help_text='Optional terminal, transfer, or gateway reference metadata.',
    )
    transaction_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional structured metadata for reconciliation or future provider integration.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Optional notes about the payment.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['sale', '-created_at']),
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(sale__isnull=False, order__isnull=True)
                    | models.Q(sale__isnull=True, order__isnull=False)
                ),
                name='payment_has_exactly_one_transaction',
            )
        ]

    def __str__(self):
        return f"Payment {self.payment_reference} - {self.get_payment_status_display()}"

    def clean(self):
        super().clean()

        if self.amount < 0:
            raise ValidationError({'amount': 'Payment amount cannot be negative.'})
        if self.amount == Decimal('0.00'):
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})

        if self.sale is None and self.order is None:
            raise ValidationError(
                'A payment must belong to either a sale or an order.'
            )
        if self.sale and self.order:
            raise ValidationError(
                'A payment cannot be linked to both a sale and an order at the same time.'
            )

        if self.customer and self.customer.role != 'CUSTOMER':
            raise ValidationError({'customer': 'Only customers can be assigned to payment records.'})

        if self.cashier and self.cashier.role not in ['CASHIER', 'MANAGER', 'OWNER']:
            raise ValidationError({'cashier': 'Only staff can process payment records.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.payment_status in [self.PaymentStatus.COMPLETED, self.PaymentStatus.REFUNDED]:
            raise ValidationError(
                'Completed or refunded payments cannot be deleted. Preserve the historical record.'
            )
        return super().delete(*args, **kwargs)
