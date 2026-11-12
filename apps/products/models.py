from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class ProductCategory(models.Model):
    """Catalog category used to group related products."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Product Category'
        verbose_name_plural = 'Product Categories'
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """Product catalog entry kept separate from Inventory stock logic."""

    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='products',
    )
    name = models.CharField(max_length=220)
    slug = models.SlugField(max_length=255, unique=True)
    sku = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
    )
    reorder_level = models.PositiveIntegerField(default=0)
    allow_pay_on_delivery = models.BooleanField(
        default=True,
        help_text="Designates whether customers can pay on delivery for this product.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['sku']),
            models.Index(fields=['slug']),
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(selling_price__gte=0),
                name='product_selling_price_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(cost_price__isnull=True) | models.Q(cost_price__gte=0),
                name='product_cost_price_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(reorder_level__gte=0),
                name='product_reorder_level_non_negative',
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.selling_price < Decimal('0.00'):
            raise ValidationError({'selling_price': 'Selling price cannot be negative.'})
        if self.cost_price is not None and self.cost_price < Decimal('0.00'):
            raise ValidationError({'cost_price': 'Cost price cannot be negative.'})
        if self.cost_price is not None and self.selling_price < self.cost_price:
            raise ValidationError({'selling_price': 'Selling price cannot be lower than cost price.'})
        if self.reorder_level < 0:
            raise ValidationError({'reorder_level': 'Reorder level cannot be negative.'})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def current_stock(self):
        """Authoritative current physical stock count from InventoryItem."""
        try:
            return self.inventory_item.quantity if hasattr(self, 'inventory_item') and self.inventory_item else 0
        except Exception:
            return 0

    @property
    def stock_quantity(self):
        """Convenience alias for current_stock."""
        return self.current_stock

    @property
    def primary_image(self):
        primary = self.images.filter(is_primary=True).order_by('display_order', 'created_at').first()
        if not primary:
            primary = self.images.order_by('display_order', 'created_at').first()
        return primary

    @property
    def image_url(self):
        """URL of the primary or first product image, or None."""
        img = self.primary_image
        return img.image.url if (img and img.image) else None

    @property
    def gross_profit(self):
        """Gross profit per unit = Selling price - Cost price."""
        cost = self.cost_price if self.cost_price is not None else Decimal('0.00')
        return self.selling_price - cost

    @property
    def gross_margin_percentage(self):
        """
        Gross profit margin percentage = ((Selling price - Cost price) / Selling price) * 100
        when selling price is greater than zero.
        """
        if not self.selling_price or self.selling_price <= Decimal('0.00'):
            return Decimal('0.00')
        cost = self.cost_price if self.cost_price is not None else Decimal('0.00')
        profit = self.selling_price - cost
        margin = (profit / self.selling_price) * Decimal('100')
        return margin.quantize(Decimal('0.01'))

    def record_price_change(self, new_price=None, changed_by=None, reason='', *, new_selling_price=None, new_cost_price=None):
        """
        Atomically record a price change (selling price, cost price, or both) and
        create an immutable ProductPriceHistory audit log record.
        Enforces selling_price >= cost_price.
        Returns the created ProductPriceHistory instance, or None if no prices changed.
        """
        from decimal import InvalidOperation
        from django.db import transaction

        target_selling = new_selling_price if new_selling_price is not None else new_price
        if target_selling is not None:
            try:
                target_selling = Decimal(str(target_selling))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({'new_price': 'Selling price must be a valid decimal.'})
            if target_selling < Decimal('0.00'):
                raise ValidationError({'new_price': 'Selling price cannot be negative.'})
        else:
            target_selling = self.selling_price

        if new_cost_price is not None:
            try:
                target_cost = Decimal(str(new_cost_price))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({'new_cost_price': 'Cost price must be a valid decimal.'})
            if target_cost < Decimal('0.00'):
                raise ValidationError({'new_cost_price': 'Cost price cannot be negative.'})
        else:
            target_cost = self.cost_price

        if target_cost is not None and target_selling < target_cost:
            raise ValidationError({'new_price': 'Selling price cannot be lower than cost price.'})

        selling_changed = (target_selling != self.selling_price)
        cost_changed = (target_cost != self.cost_price)

        if not selling_changed and not cost_changed:
            return None

        with transaction.atomic():
            prev_selling = self.selling_price
            prev_cost = self.cost_price

            self.selling_price = target_selling
            self.cost_price = target_cost
            self.save(update_fields=['selling_price', 'cost_price', 'updated_at'])

            history = ProductPriceHistory.objects.create(
                product=self,
                previous_price=prev_selling,
                new_price=self.selling_price,
                previous_cost_price=prev_cost,
                new_cost_price=self.cost_price,
                changed_by=changed_by,
                reason=reason or '',
            )
            return history


class ProductImage(models.Model):
    """Image associated with a product, with one primary image allowed per product."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    display_order = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'created_at']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
            models.Index(fields=['product', 'display_order']),
        ]

    def __str__(self):
        return f"{self.product.name} image {self.display_order}"

    @property
    def url(self):
        """Direct URL to the uploaded image file."""
        return self.image.url if self.image else ''

    def clean(self):
        super().clean()
        if self.is_primary:
            existing_primary = ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).first()
            if existing_primary:
                raise ValidationError({'is_primary': 'Only one primary image is allowed for each product.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductPriceHistory(models.Model):
    """
    Immutable historical audit record of product selling price and cost price revisions.
    Maintains historical snapshots for auditing, compliance, and margin analysis.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_history',
    )
    previous_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    previous_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    new_cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_price_changes',
    )
    reason = models.CharField(max_length=200, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Product Price History'
        verbose_name_plural = 'Product Price Histories'
        indexes = [
            models.Index(fields=['product', 'changed_at']),
            models.Index(fields=['changed_by']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(previous_price__gte=0),
                name='product_price_history_previous_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(new_price__gte=0),
                name='product_price_history_new_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(previous_cost_price__isnull=True) | models.Q(previous_cost_price__gte=0),
                name='product_price_history_prev_cost_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(new_cost_price__isnull=True) | models.Q(new_cost_price__gte=0),
                name='product_price_history_new_cost_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.product.name}: ₦{self.previous_price} -> ₦{self.new_price}"

    @property
    def previous_selling_price(self):
        return self.previous_price

    @property
    def new_selling_price(self):
        return self.new_price

    @property
    def previous_gross_profit(self):
        cost = self.previous_cost_price if self.previous_cost_price is not None else Decimal('0.00')
        return self.previous_price - cost

    @property
    def new_gross_profit(self):
        cost = self.new_cost_price if self.new_cost_price is not None else Decimal('0.00')
        return self.new_price - cost

    @property
    def previous_gross_margin_percentage(self):
        if not self.previous_price or self.previous_price <= Decimal('0.00'):
            return Decimal('0.00')
        cost = self.previous_cost_price if self.previous_cost_price is not None else Decimal('0.00')
        return (((self.previous_price - cost) / self.previous_price) * Decimal('100')).quantize(Decimal('0.01'))

    @property
    def new_gross_margin_percentage(self):
        if not self.new_price or self.new_price <= Decimal('0.00'):
            return Decimal('0.00')
        cost = self.new_cost_price if self.new_cost_price is not None else Decimal('0.00')
        return (((self.new_price - cost) / self.new_price) * Decimal('100')).quantize(Decimal('0.1'))

    @property
    def gross_profit(self):
        """Current/new gross profit snapshot."""
        return self.new_gross_profit

    @property
    def gross_margin_percentage(self):
        """Current/new gross profit margin percentage snapshot."""
        return self.new_gross_margin_percentage

    def delete(self, *args, **kwargs):
        raise ValidationError('Price history records are immutable and cannot be deleted.')

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Price history records are immutable and cannot be modified.')
        super().save(*args, **kwargs)
