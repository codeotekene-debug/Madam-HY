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
        if self.selling_price < 0:
            raise ValidationError({'selling_price': 'Selling price cannot be negative.'})
        if self.cost_price is not None and self.cost_price < 0:
            raise ValidationError({'cost_price': 'Cost price cannot be negative.'})
        if self.reorder_level < 0:
            raise ValidationError({'reorder_level': 'Reorder level cannot be negative.'})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def primary_image(self):
        return self.images.filter(is_primary=True).order_by('display_order', 'created_at').first()

    def record_price_change(self, new_price, changed_by=None, reason=''):
        if new_price < 0:
            raise ValidationError({'new_price': 'New price cannot be negative.'})

        previous_price = self.selling_price
        if Decimal(str(new_price)) == previous_price:
            return None

        self.selling_price = Decimal(str(new_price))
        self.save(update_fields=['selling_price', 'updated_at'])

        history = ProductPriceHistory.objects.create(
            product=self,
            previous_price=previous_price,
            new_price=self.selling_price,
            changed_by=changed_by,
            reason=reason,
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
    """Historical record of product selling price changes."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_history',
    )
    previous_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
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
        ]

    def __str__(self):
        return f"{self.product.name}: {self.previous_price} -> {self.new_price}"
