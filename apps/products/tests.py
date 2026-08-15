from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Product, ProductCategory, ProductImage, ProductPriceHistory


class ProductModelsTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(
            name="Fashion",
            slug="fashion",
            description="Fashion and lifestyle products",
        )

        self.product = Product.objects.create(
            name="Green Ankara Fabric Premium",
            slug="green-ankara-fabric-premium",
            sku="MH-FAB-104",
            category=self.category,
            description="Premium fabric for boutique retail.",
            selling_price=Decimal("12500.00"),
            cost_price=Decimal("9300.00"),
            reorder_level=8,
        )

    def test_category_creation_works(self):
        self.assertEqual(self.category.name, "Fashion")
        self.assertEqual(self.category.slug, "fashion")
        self.assertTrue(self.category.is_active)

    def test_product_creation_works(self):
        self.assertEqual(self.product.sku, "MH-FAB-104")
        self.assertEqual(self.product.category, self.category)
        self.assertTrue(self.product.is_active)

    def test_sku_must_be_unique(self):
        duplicate = Product(
            name="Other Product",
            slug="other-product",
            sku="MH-FAB-104",
            category=self.category,
            selling_price=Decimal("2000.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_multiple_images_can_belong_to_one_product(self):
        ProductImage.objects.create(
            product=self.product,
            image="products/demo-1.jpg",
            alt_text="Front view",
            display_order=1,
            is_primary=True,
        )
        ProductImage.objects.create(
            product=self.product,
            image="products/demo-2.jpg",
            alt_text="Rear view",
            display_order=2,
            is_primary=False,
        )

        self.assertEqual(self.product.images.count(), 2)

    def test_only_one_primary_image_is_allowed(self):
        ProductImage.objects.create(
            product=self.product,
            image="products/demo-1.jpg",
            alt_text="Primary image",
            display_order=1,
            is_primary=True,
        )

        duplicate_primary = ProductImage(
            product=self.product,
            image="products/demo-2.jpg",
            alt_text="Another primary",
            display_order=2,
            is_primary=True,
        )

        with self.assertRaises(ValidationError):
            duplicate_primary.save()

    def test_price_history_can_be_recorded(self):
        history = self.product.record_price_change(
            new_price=Decimal("13500.00"),
            reason="Seasonal update",
        )

        self.assertEqual(history.previous_price, Decimal("12500.00"))
        self.assertEqual(history.new_price, Decimal("13500.00"))
        self.assertEqual(self.product.price_history.count(), 1)

    def test_negative_monetary_values_are_rejected(self):
        invalid_product = Product(
            name="Invalid Product",
            slug="invalid-product",
            sku="MH-NEG-001",
            category=self.category,
            selling_price=Decimal("-10.00"),
            cost_price=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            invalid_product.full_clean()

    def test_django_system_checks_pass(self):
        from django.core.management import call_command

        call_command('check')
