from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify


class Sale(models.Model):
    """Point of Sale transaction record."""

    class SaleStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        TRANSFER = 'TRANSFER', 'Bank Transfer'
        CARD = 'CARD', 'Card'
        CREDIT = 'CREDIT', 'Credit'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    sale_number = models.CharField(
        max_length=50,
        unique=True,
        help_text='Unique sale/receipt identifier (e.g., MH-XXXXXX).',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text='Customer for the sale. Required for credit sales. Optional for walk-in cash sales.',
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processed_sales',
        help_text='Staff member who processed the sale.',
    )
    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.DRAFT,
        help_text='Sale lifecycle status. Only COMPLETED sales affect inventory.',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        help_text='Payment method used or intended for the sale.',
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        help_text='Payment completion status. For future Payments module integration.',
    )
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Sum of all SaleItem line totals before discount.',
    )
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Sale-level discount amount.',
    )
    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Final sale total after discount (subtotal - discount).',
    )
    amount_received = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Amount received from customer (for cash or other methods).',
    )
    change_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Change given to customer (amount_received - total).',
    )
    notes = models.TextField(
        blank=True,
        help_text='Optional internal notes about the sale.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sale'
        verbose_name_plural = 'Sales'
        indexes = [
            models.Index(fields=['sale_number']),
            models.Index(fields=['status']),
            models.Index(fields=['cashier', '-created_at']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Sale {self.sale_number} - {self.get_status_display()}"

    def clean(self):
        super().clean()
        # Validate credit sales require a customer
        if self.payment_method == self.PaymentMethod.CREDIT and not self.customer:
            raise ValidationError(
                {'customer': 'Customer is required for credit sales.'}
            )
        # Validate credit sales require customer role
        if self.payment_method == self.PaymentMethod.CREDIT and self.customer:
            if self.customer.role != 'CUSTOMER':
                raise ValidationError(
                    {'customer': 'Only customers (role=CUSTOMER) can use credit.'}
                )
        # Validate cashier is staff or owner
        if self.cashier and self.cashier.role not in ['CASHIER', 'MANAGER', 'OWNER']:
            raise ValidationError(
                {'cashier': 'Only staff can process sales.'}
            )
        # Validate monetary fields are non-negative
        if self.subtotal < 0:
            raise ValidationError({'subtotal': 'Subtotal cannot be negative.'})
        if self.discount < 0:
            raise ValidationError({'discount': 'Discount cannot be negative.'})
        if self.total < 0:
            raise ValidationError({'total': 'Total cannot be negative.'})
        if self.amount_received is not None and self.amount_received < 0:
            raise ValidationError({'amount_received': 'Amount received cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """
        Recalculate sale totals from SaleItems.

        Updates subtotal and total based on current items.
        Does not persist changes; caller must save().
        """
        items = self.items.all()
        self.subtotal = sum(
            item.unit_price * item.quantity for item in items
        )
        self.total = max(self.subtotal - self.discount, Decimal('0.00'))
        return self

    @transaction.atomic
    def complete_sale(self):
        """
        Finalize the sale and deduct inventory if applicable.

        This method:
        1. Validates the sale is in DRAFT status
        2. Validates the sale has items
        3. Validates sufficient inventory for each item
        4. Deducts inventory using InventoryItem.adjust_stock()
        5. Creates StockMovement records
        6. Sets status to COMPLETED
        7. Entire operation is atomic; rollback on any failure

        Raises:
            ValidationError: If sale is invalid, has no items, or inventory is insufficient
        """
        if self.status != self.SaleStatus.DRAFT:
            raise ValidationError(
                f'Only DRAFT sales can be completed. Current status: {self.get_status_display()}'
            )

        items = self.items.select_related('product__inventory_item').all()
        if not items.exists():
            raise ValidationError('Sale must have at least one item before completing.')

        # Validate and collect all inventory requirements upfront
        inventory_operations = []
        for item in items:
            if not hasattr(item.product, 'inventory_item'):
                raise ValidationError(
                    f'Product {item.product.name} does not have inventory tracking.'
                )
            inventory = item.product.inventory_item
            if inventory.quantity < item.quantity:
                raise ValidationError(
                    f'Insufficient stock for {item.product.name}. '
                    f'Required: {item.quantity}, Available: {inventory.quantity}'
                )
            inventory_operations.append((inventory, item))

        # Execute all inventory deductions atomically
        for inventory, item in inventory_operations:
            inventory.adjust_stock(
                quantity_delta=-item.quantity,
                reason='Sale',
                reference=self.sale_number,
                created_by=self.cashier,
                movement_type='STOCK_OUT',
            )

        # Mark sale as completed
        self.status = self.SaleStatus.COMPLETED
        self.payment_status = self.PaymentStatus.COMPLETED
        self.save(update_fields=['status', 'payment_status', 'updated_at'])

    @transaction.atomic
    def cancel_sale(self):
        """
        Cancel the sale.

        Currently, cancelling a COMPLETED sale does NOT reverse inventory deductions.
        Return/reversal functionality belongs to a future phase.

        Only COMPLETED sales can be cancelled.

        Raises:
            ValidationError: If sale is already cancelled or still in draft.
        """
        if self.status == self.SaleStatus.CANCELLED:
            raise ValidationError('Sale is already cancelled.')
        if self.status == self.SaleStatus.DRAFT:
            raise ValidationError('Use delete() to remove draft sales, or complete before cancelling.')

        self.status = self.SaleStatus.CANCELLED
        self.save(update_fields=['status', 'updated_at'])


class SaleItem(models.Model):
    """Line item in a Sale transaction, with price snapshots for historical accuracy."""

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='items',
        help_text='Sale this item belongs to.',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='sale_items',
        help_text='Product sold (historical reference; use snapshots for display).',
    )
    quantity = models.PositiveIntegerField(
        help_text='Quantity sold.',
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Product selling price at time of sale (price snapshot).',
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        help_text='Optional line-item discount.',
    )
    product_name_snapshot = models.CharField(
        max_length=220,
        help_text='Product name at time of sale.',
    )
    sku_snapshot = models.CharField(
        max_length=80,
        help_text='Product SKU at time of sale.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Sale Item'
        verbose_name_plural = 'Sale Items'
        indexes = [
            models.Index(fields=['sale']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.sale.sale_number} - {self.product_name_snapshot} x{self.quantity}"

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be positive.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})
        if self.discount < 0:
            raise ValidationError({'discount': 'Discount cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        """Calculate line total: (quantity × unit_price) - discount."""
        return (self.quantity * self.unit_price) - self.discount

    @classmethod
    def create_from_product(cls, product, sale, quantity, discount=Decimal('0.00')):
        """
        Factory method to create a SaleItem with product snapshots.

        Args:
            product: Product instance to create item from
            sale: Sale instance to associate with
            quantity: Quantity to sell
            discount: Optional line-level discount

        Returns:
            SaleItem instance (not yet saved)

        Raises:
            ValidationError: If product or parameters are invalid
        """
        if not product:
            raise ValidationError('Product is required.')
        if quantity <= 0:
            raise ValidationError('Quantity must be positive.')

        item = cls(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=product.selling_price,
            discount=discount,
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
        )
        return item
