from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class InventoryItem(models.Model):
    """Current stock quantity for a single product."""

    product = models.OneToOneField(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='inventory_item',
    )
    quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product__name']
        verbose_name = 'Inventory Item'
        verbose_name_plural = 'Inventory Items'
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['quantity']),
        ]

    def __str__(self):
        return f'{self.product.name} ({self.quantity} in stock)'

    def clean(self):
        super().clean()
        if self.quantity < 0:
            raise ValidationError({'quantity': 'Inventory quantity cannot be negative.'})

    @property
    def reorder_level(self):
        return self.product.reorder_level

    @property
    def is_low_stock(self):
        return self.quantity > 0 and self.quantity <= self.product.reorder_level

    @property
    def is_out_of_stock(self):
        return self.quantity == 0

    @property
    def stock_status(self):
        if self.quantity == 0:
            return 'OUT_OF_STOCK'
        if self.quantity <= self.product.reorder_level:
            return 'LOW_STOCK'
        return 'IN_STOCK'

    @transaction.atomic
    def adjust_stock(self, quantity_delta, reason='', reference='', created_by=None, movement_type='ADJUSTMENT'):
        if quantity_delta == 0:
            raise ValidationError({'quantity': 'Movement quantity cannot be zero.'})

        previous_quantity = self.quantity
        new_quantity = previous_quantity + quantity_delta

        if new_quantity < 0:
            raise ValidationError({'quantity': 'Stock cannot become negative.'})

        self.quantity = new_quantity
        self.full_clean()
        self.save(update_fields=['quantity', 'updated_at'])

        movement = StockMovement(
            inventory_item=self,
            product=self.product,
            movement_type=movement_type,
            quantity=quantity_delta,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            reason=reason,
            reference=reference,
            created_by=created_by,
        )
        movement.full_clean()
        movement.save()

        return self


class StockMovement(models.Model):
    """Historical record of stock changes for audit and reconciliation."""

    class MovementType(models.TextChoices):
        STOCK_IN = 'STOCK_IN', 'Stock In'
        STOCK_OUT = 'STOCK_OUT', 'Stock Out'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        RETURN = 'RETURN', 'Return'
        DAMAGE = 'DAMAGE', 'Damage'
        CORRECTION = 'CORRECTION', 'Correction'

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='movements',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='inventory_movements',
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        default=MovementType.ADJUSTMENT,
    )
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reason = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['movement_type']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return f'{self.product.name} {self.movement_type}: {self.quantity}'

    def clean(self):
        super().clean()
        if self.quantity == 0:
            raise ValidationError({'quantity': 'Movement quantity cannot be zero.'})
        if self.previous_quantity < 0 or self.new_quantity < 0:
            raise ValidationError({'quantity': 'Stock values cannot be negative.'})
        if self.inventory_item.product_id != self.product_id:
            raise ValidationError({'product': 'Movement product must match the inventory item product.'})
        if self.new_quantity != self.previous_quantity + self.quantity:
            raise ValidationError({'quantity': 'Movement quantity must match the stock delta.'})
