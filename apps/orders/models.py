from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Order(models.Model):
    """Customer order record (separate from POS Sales)."""

    class OrderStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        PROCESSING = 'PROCESSING', 'Processing'
        READY = 'READY', 'Ready'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        TRANSFER = 'TRANSFER', 'Bank Transfer'
        CARD = 'CARD', 'Card'
        CREDIT = 'CREDIT', 'Credit'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'

    order_number = models.CharField(
        max_length=50,
        unique=True,
        help_text='Unique order identifier (e.g., MH-ORD-10501).',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text='Customer who placed the order.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_orders',
        help_text='Staff member who created/received the order.',
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        help_text='Order lifecycle status. Does not affect inventory until fulfillment.',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        help_text='Intended payment method for the order.',
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        help_text='Payment confirmation status. For future Payments module integration.',
    )
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Sum of all OrderItem line totals before discount.',
    )
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Order-level discount amount.',
    )
    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Final order total after discount (subtotal - discount).',
    )
    delivery_address = models.TextField(
        blank=True,
        help_text='Delivery address for the order.',
    )
    customer_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text='Customer contact phone number.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Optional internal notes about the order.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['status']),
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Order {self.order_number} - {self.get_status_display()}"

    def clean(self):
        super().clean()
        # Validate monetary fields are non-negative
        if self.subtotal < 0:
            raise ValidationError({'subtotal': 'Subtotal cannot be negative.'})
        if self.discount < 0:
            raise ValidationError({'discount': 'Discount cannot be negative.'})
        if self.total < 0:
            raise ValidationError({'total': 'Total cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """
        Recalculate order totals from OrderItems.

        Updates subtotal and total based on current items.
        Does not persist changes; caller must save().
        """
        items = self.items.all()
        self.subtotal = sum(
            item.unit_price * item.quantity for item in items
        )
        self.total = max(self.subtotal - self.discount, Decimal('0.00'))
        return self

    def transition_to(self, new_status):
        """Move the order through the supported lifecycle without side effects."""
        transitions = {
            self.OrderStatus.PENDING: {
                self.OrderStatus.CONFIRMED,
                self.OrderStatus.CANCELLED,
            },
            self.OrderStatus.CONFIRMED: {
                self.OrderStatus.PROCESSING,
                self.OrderStatus.CANCELLED,
            },
            self.OrderStatus.PROCESSING: {
                self.OrderStatus.READY,
                self.OrderStatus.CANCELLED,
            },
            self.OrderStatus.READY: {
                self.OrderStatus.COMPLETED,
                self.OrderStatus.CANCELLED,
            },
            self.OrderStatus.COMPLETED: set(),
            self.OrderStatus.CANCELLED: set(),
        }
        valid_statuses = {choice.value for choice in self.OrderStatus}
        if new_status not in valid_statuses:
            raise ValidationError({'status': 'Invalid order status.'})
        if new_status not in transitions.get(self.status, set()):
            raise ValidationError(
                {'status': f'Cannot transition order from {self.status} to {new_status}.'}
            )
        self.status = new_status
        return self


class OrderItem(models.Model):
    """Line item in an Order, with price snapshots for historical accuracy."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        help_text='Order this item belongs to.',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='order_items',
        help_text='Product ordered (historical reference; use snapshots for display).',
    )
    quantity = models.PositiveIntegerField(
        help_text='Quantity ordered.',
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Product price at time of order (price snapshot).',
    )
    product_name_snapshot = models.CharField(
        max_length=220,
        help_text='Product name at time of order.',
    )
    sku_snapshot = models.CharField(
        max_length=80,
        help_text='Product SKU at time of order.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.product_name_snapshot} x{self.quantity}"

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be positive.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        """Calculate line total: quantity × unit_price."""
        return self.quantity * self.unit_price

    @classmethod
    def create_from_product(cls, product, order, quantity):
        """
        Factory method to create an OrderItem with product snapshots.

        Args:
            product: Product instance to create item from
            order: Order instance to associate with
            quantity: Quantity to order

        Returns:
            OrderItem instance (not yet saved)

        Raises:
            ValidationError: If product or parameters are invalid
        """
        if not product:
            raise ValidationError('Product is required.')
        if quantity <= 0:
            raise ValidationError('Quantity must be positive.')

        item = cls(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=product.selling_price,
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
        )
        return item
