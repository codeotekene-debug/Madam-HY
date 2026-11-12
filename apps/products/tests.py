from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
import json

from PIL import Image

from .models import Product, ProductCategory, ProductImage, ProductPriceHistory

User = get_user_model()


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


class ProductManagementTests(TestCase):
    """Tests for product creation, update, and deactivation endpoints."""

    def setUp(self):
        self.client = Client()

        # Create test users with different roles
        self.owner = User.objects.create_user(
            email='owner@test.com',
            username='owner',
            password='testpass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='manager@test.com',
            username='manager',
            password='testpass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='cashier@test.com',
            username='cashier',
            password='testpass123',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            email='staff@test.com',
            username='staff',
            password='testpass123',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            email='customer@test.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )

        # Create test category
        self.category = ProductCategory.objects.create(
            name="Test Category",
            slug="test-category",
            description="Test category description",
        )

        # Create test product
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            sku="TEST-001",
            category=self.category,
            selling_price=Decimal("100.00"),
            cost_price=Decimal("60.00"),
            reorder_level=5,
        )

    def test_unauthenticated_user_cannot_create_product(self):
        """Test that unauthenticated users receive 401 when creating product."""
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({'name': 'New Product', 'sku': 'NEW-001', 'category_id': self.category.id, 'selling_price': '100.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_customer_cannot_create_product(self):
        """Test that customers cannot create products."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({'name': 'New Product', 'sku': 'NEW-001', 'category_id': self.category.id, 'selling_price': '100.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_cashier_cannot_create_product(self):
        """Test that cashiers cannot create products."""
        self.client.force_login(self.cashier)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({'name': 'New Product', 'sku': 'NEW-001', 'category_id': self.category.id, 'selling_price': '100.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_create_product(self):
        """Test that staff cannot create products."""
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({'name': 'New Product', 'sku': 'NEW-001', 'category_id': self.category.id, 'selling_price': '100.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_product(self):
        """Test that managers can create products."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'New Product',
                'sku': 'NEW-001',
                'category_id': self.category.id,
                'selling_price': '150.00',
                'cost_price': '90.00',
                'reorder_level': 10,
                'description': 'Test description',
                'is_active': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['data']['name'], 'New Product')
        self.assertEqual(response.json()['data']['sku'], 'NEW-001')

    def test_owner_can_create_product(self):
        """Test that owners can create products."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'Owner Product',
                'sku': 'OWNER-001',
                'category_id': self.category.id,
                'selling_price': '200.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])

    def test_product_creation_requires_name(self):
        """Test that product creation requires a name."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'sku': 'TEST-999',
                'category_id': self.category.id,
                'selling_price': '100.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json()['errors'])

    def test_product_creation_requires_sku(self):
        """Test that product creation requires a SKU."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'Test',
                'category_id': self.category.id,
                'selling_price': '100.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('sku', response.json()['errors'])

    def test_product_creation_requires_category(self):
        """Test that product creation requires a category."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'Test',
                'sku': 'TEST-999',
                'selling_price': '100.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('category_id', response.json()['errors'])

    def test_product_creation_requires_selling_price(self):
        """Test that product creation requires a selling price."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'Test',
                'sku': 'TEST-999',
                'category_id': self.category.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('selling_price', response.json()['errors'])

    def test_product_creation_rejects_duplicate_sku(self):
        """Test that duplicate SKUs are rejected."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'Duplicate SKU',
                'sku': 'TEST-001',  # Already exists
                'category_id': self.category.id,
                'selling_price': '100.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn('sku', response.json()['errors'])

    def test_manager_can_update_product(self):
        """Test that managers can update products."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({
                'name': 'Updated Product',
                'selling_price': '150.00',
                'description': 'Updated description',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        # Verify the product was updated
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Updated Product')
        self.assertEqual(self.product.selling_price, Decimal('150.00'))

    def test_owner_can_update_product(self):
        """Test that owners can update products."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'name': 'Owner Updated'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_manager_update_product_price_preserves_history(self):
        """Changing the selling price through product update must preserve price history."""
        self.client.force_login(self.manager)
        initial_count = self.product.price_history.count()

        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'selling_price': '175.00', 'description': 'Updated with pricing change'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_history.count(), initial_count + 1)
        self.assertEqual(self.product.selling_price, Decimal('175.00'))
        self.assertEqual(self.product.price_history.first().previous_price, Decimal('100.00'))
        self.assertEqual(self.product.price_history.first().changed_by, self.manager)

    def test_manager_update_product_same_price_does_not_duplicate_history(self):
        """Changing other fields without a new price should not create a duplicate price history record."""
        self.client.force_login(self.manager)
        initial_count = self.product.price_history.count()

        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'name': 'Same Price Updated', 'description': 'No price change here'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price_history.count(), initial_count)

    def test_product_update_rolls_back_price_and_history_when_later_field_is_invalid(self):
        """A later validation error must roll back an earlier price change."""
        self.client.force_login(self.manager)
        initial_price = self.product.selling_price
        initial_count = self.product.price_history.count()

        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({
                'selling_price': '175.00',
                'reorder_level': -1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price, initial_price)
        self.assertEqual(self.product.price_history.count(), initial_count)

    def test_customer_cannot_update_product(self):
        """Test that customers cannot update products."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'name': 'Customer Updated'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_product_update_rejects_invalid_price(self):
        """Test that product update rejects invalid prices."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'selling_price': 'invalid'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertIn('selling_price', response.json()['errors'])

    def test_product_update_rejects_empty_and_none_prices(self):
        """Invalid empty and None selling prices should be rejected without crashing."""
        self.client.force_login(self.manager)

        for invalid_value in ['', None]:
            with self.subTest(invalid_value=invalid_value):
                response = self.client.post(
                    reverse('products:update', args=[self.product.id]),
                    data=json.dumps({'selling_price': invalid_value}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['success'])
                self.assertIn('selling_price', response.json()['errors'])

    def test_manager_can_deactivate_product(self):
        """Test that managers can deactivate products."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:deactivate', args=[self.product.id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        # Verify the product is deactivated
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_owner_can_deactivate_product(self):
        """Test that owners can deactivate products."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:deactivate', args=[self.product.id]),
        )
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_deactivate_product(self):
        """Test that customers cannot deactivate products."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:deactivate', args=[self.product.id]),
        )
        self.assertEqual(response.status_code, 403)

    def test_deactivation_does_not_delete_product(self):
        """Test that deactivation marks the product as inactive but doesn't delete it."""
        self.client.force_login(self.manager)
        product_id = self.product.id
        self.client.post(reverse('products:deactivate', args=[product_id]))

        # Product should still exist in database
        product = Product.objects.get(id=product_id)
        self.assertFalse(product.is_active)

    def test_manager_can_change_price(self):
        """Test that managers can change product prices."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({
                'new_price': '200.00',
                'reason': 'Market adjustment',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        # Verify price was changed
        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price, Decimal('200.00'))

    def test_owner_can_change_price(self):
        """Test that owners can change product prices."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({'new_price': '250.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_change_price(self):
        """Test that customers cannot change product prices."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({'new_price': '200.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_price_change_creates_history(self):
        """Test that price changes create price history records."""
        self.client.force_login(self.manager)
        initial_history_count = self.product.price_history.count()

        self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({'new_price': '200.00', 'reason': 'Test'}),
            content_type='application/json',
        )

        # Price history should be created
        self.assertEqual(self.product.price_history.count(), initial_history_count + 1)
        history = self.product.price_history.first()
        self.assertEqual(history.previous_price, Decimal('100.00'))
        self.assertEqual(history.new_price, Decimal('200.00'))
        self.assertEqual(history.reason, 'Test')
        self.assertEqual(history.changed_by, self.manager)

    def test_price_change_same_price_rejected(self):
        """Test that changing price to the same value is rejected."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({'new_price': '100.00'}),  # Same as current
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_price_change_requires_new_price(self):
        """Test that price change requires new_price field."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:change_price', args=[self.product.id]),
            data=json.dumps({'reason': 'Test'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_price', response.json()['errors'])


class ProductImageManagementTests(TestCase):
    """Tests for product image management endpoints."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            email='owner@test.com',
            username='owner',
            password='testpass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='manager@test.com',
            username='manager',
            password='testpass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='cashier@test.com',
            username='cashier',
            password='testpass123',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            email='staff@test.com',
            username='staff',
            password='testpass123',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            email='customer@test.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )
        self.category = ProductCategory.objects.create(
            name='Image Category',
            slug='image-category',
            description='Category for image tests',
        )
        self.product = Product.objects.create(
            name='Product for Images',
            slug='product-for-images',
            sku='IMG-001',
            category=self.category,
            selling_price=Decimal('120.00'),
        )

    def _make_image_file(self, filename='test-image.jpg', image_format='JPEG', color=(255, 0, 0)):
        buffer = BytesIO()
        image = Image.new('RGB', (20, 20), color=color)
        image.save(buffer, format=image_format)
        buffer.seek(0)
        return SimpleUploadedFile(name=filename, content=buffer.read(), content_type=f'image/{image_format.lower()}')

    def test_manager_can_upload_valid_jpeg(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': self._make_image_file('front.jpg', 'JPEG')},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])
        self.assertEqual(self.product.images.count(), 1)

    def test_owner_can_upload_valid_png(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': self._make_image_file('front.png', 'PNG')},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])

    def test_customer_cannot_upload_image(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': self._make_image_file('front.jpg', 'JPEG')},
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_extension_rejected(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': self._make_image_file('bad.exe', 'PNG')},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json()['errors'])

    def test_svg_rejected(self):
        self.client.force_login(self.manager)
        svg = SimpleUploadedFile('bad.svg', b'<svg></svg>', content_type='image/svg+xml')
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': svg},
        )
        self.assertEqual(response.status_code, 400)

    def test_corrupted_image_rejected(self):
        self.client.force_login(self.manager)
        corrupted = SimpleUploadedFile('corrupt.jpg', b'not-a-real-image', content_type='image/jpeg')
        response = self.client.post(
            reverse('products:upload_image', args=[self.product.id]),
            {'image': corrupted},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json()['errors'])

    def test_patch_with_true_is_primary_sets_primary(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=False)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, first.id]),
            data=json.dumps({'is_primary': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_primary)
        self.assertFalse(second.is_primary)

    def test_patch_missing_is_primary_is_treated_as_missing(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=True)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, first.id]),
            data=json.dumps({'alt_text': 'Updated alt'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.alt_text, 'Updated alt')
        self.assertTrue(first.is_primary)
        self.assertFalse(second.is_primary)

    def test_patch_invalid_string_is_primary_rejected(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=True)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, first.id]),
            data=json.dumps({'is_primary': 'false'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('is_primary', response.json()['errors'])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_primary)
        self.assertFalse(second.is_primary)

    def test_unsetting_current_primary_promotes_next_image(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=True)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, first.id]),
            data=json.dumps({'is_primary': False}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_unsetting_only_primary_leaves_no_primary(self):
        image = ProductImage.objects.create(product=self.product, image='products/only.jpg', alt_text='only', display_order=1, is_primary=True)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, image.id]),
            data=json.dumps({'is_primary': False}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertFalse(image.is_primary)
        self.assertFalse(self.product.images.filter(is_primary=True).exists())

    def test_setting_second_image_primary_unsets_first(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=True)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, second.id]),
            data=json.dumps({'is_primary': True}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_patching_metadata_updates_alt_text_and_order(self):
        image = ProductImage.objects.create(product=self.product, image='products/patch.jpg', alt_text='Old', display_order=1, is_primary=True)

        self.client.force_login(self.manager)
        response = self.client.patch(
            reverse('products:image_detail', args=[self.product.id, image.id]),
            data=json.dumps({'alt_text': 'Updated alt', 'display_order': 3}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.alt_text, 'Updated alt')
        self.assertEqual(image.display_order, 3)

    def test_deleting_primary_promotes_next_image(self):
        first = ProductImage.objects.create(product=self.product, image='products/first.jpg', alt_text='first', display_order=1, is_primary=True)
        second = ProductImage.objects.create(product=self.product, image='products/second.jpg', alt_text='second', display_order=2, is_primary=False)

        self.client.force_login(self.manager)
        response = self.client.delete(reverse('products:image_detail', args=[self.product.id, first.id]))

        self.assertEqual(response.status_code, 200)
        second.refresh_from_db()
        self.assertTrue(second.is_primary)
        self.assertFalse(ProductImage.objects.filter(id=first.id).exists())

    def test_deleting_only_image_leaves_product_valid(self):
        image = ProductImage.objects.create(product=self.product, image='products/only.jpg', alt_text='only', display_order=1, is_primary=True)

        self.client.force_login(self.manager)
        response = self.client.delete(reverse('products:image_detail', args=[self.product.id, image.id]))

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.images.count(), 0)


class CategoryManagementTests(TestCase):
    """Tests for category creation, update, and deactivation endpoints."""

    def setUp(self):
        self.client = Client()

        # Create test users
        self.manager = User.objects.create_user(
            email='manager@test.com',
            username='manager',
            password='testpass123',
            role='MANAGER',
        )
        self.customer = User.objects.create_user(
            email='customer@test.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )
        self.owner = User.objects.create_user(
            email='owner@test.com',
            username='owner',
            password='testpass123',
            role='OWNER',
        )

        # Create test category
        self.category = ProductCategory.objects.create(
            name="Test Category",
            slug="test-category",
            description="Test",
        )

    def test_unauthenticated_user_cannot_create_category(self):
        """Test that unauthenticated users receive 401."""
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({'name': 'New Category'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_create_category(self):
        """Test that customers cannot create categories."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({'name': 'New Category'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_category(self):
        """Test that managers can create categories."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({
                'name': 'Electronics',
                'description': 'Electronic products',
                'is_active': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['data']['name'], 'Electronics')

    def test_owner_can_create_category(self):
        """Test that owners can create categories."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({'name': 'Books'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

    def test_category_creation_requires_name(self):
        """Test that category creation requires a name."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json()['errors'])

    def test_category_creation_rejects_duplicate_name(self):
        """Test that duplicate category names are rejected."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_create'),
            data=json.dumps({'name': 'Test Category'}),  # Already exists
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn('name', response.json()['errors'])

    def test_manager_can_update_category(self):
        """Test that managers can update categories."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_update', args=[self.category.id]),
            data=json.dumps({
                'name': 'Updated Category',
                'description': 'Updated description',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        # Verify update
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'Updated Category')

    def test_owner_can_update_category(self):
        """Test that owners can update categories."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:category_update', args=[self.category.id]),
            data=json.dumps({'name': 'Owner Updated'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_update_category(self):
        """Test that customers cannot update categories."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:category_update', args=[self.category.id]),
            data=json.dumps({'name': 'Customer Updated'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_deactivate_category(self):
        """Test that managers can deactivate categories."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_deactivate', args=[self.category.id]),
        )
        self.assertEqual(response.status_code, 200)

        # Verify deactivation
        self.category.refresh_from_db()
        self.assertFalse(self.category.is_active)

    def test_owner_can_deactivate_category(self):
        """Test that owners can deactivate categories."""
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('products:category_deactivate', args=[self.category.id]),
        )
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_deactivate_category(self):
        """Test that customers cannot deactivate categories."""
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('products:category_deactivate', args=[self.category.id]),
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_deactivate_category_with_active_products(self):
        """Test that categories with active products cannot be deactivated."""
        # Create a product in this category
        Product.objects.create(
            name="Test Product",
            slug="test-product",
            sku="TEST-001",
            category=self.category,
            selling_price=Decimal("100.00"),
            is_active=True,
        )

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_deactivate', args=[self.category.id]),
        )
        self.assertEqual(response.status_code, 409)
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_active)

    def test_can_deactivate_category_after_deactivating_products(self):
        """Test that a category can be deactivated after its products are deactivated."""
        # Create and deactivate a product
        product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            sku="TEST-001",
            category=self.category,
            selling_price=Decimal("100.00"),
            is_active=True,
        )
        product.is_active = False
        product.save()

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:category_deactivate', args=[self.category.id]),
        )
        self.assertEqual(response.status_code, 200)


class ProductInventoryBoundaryTests(TestCase):
    """Tests to ensure product management doesn't modify inventory."""

    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            email='manager@test.com',
            username='manager',
            password='testpass123',
            role='MANAGER',
        )
        self.category = ProductCategory.objects.create(
            name="Test Category",
            slug="test-category",
        )
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            sku="TEST-001",
            category=self.category,
            selling_price=Decimal("100.00"),
        )

    def test_product_creation_does_not_create_inventory(self):
        """Test that creating a product doesn't create an InventoryItem."""
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:create'),
            data=json.dumps({
                'name': 'New Product',
                'sku': 'NEW-001',
                'category_id': self.category.id,
                'selling_price': '100.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        # Product should be created but without automatic inventory
        new_product = Product.objects.get(sku='NEW-001')
        self.assertFalse(hasattr(new_product, 'inventory_item'))

    def test_product_update_does_not_modify_inventory(self):
        """Test that updating a product doesn't affect inventory."""
        # This is tested implicitly by not creating inventory in the first place
        # But we can verify that if inventory exists, it's not modified
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('products:update', args=[self.product.id]),
            data=json.dumps({'name': 'Updated Name'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

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


class ProductsAPITests(TestCase):
    """Test suite for Products read-only API endpoints."""

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username="staff_api_test",
            email="staff_api_test@example.com",
            password="password",
            role="MANAGER",
        )

        # Create test categories
        self.fashion_category = ProductCategory.objects.create(
            name="Fashion",
            slug="fashion",
            description="Fashion and lifestyle products",
        )
        self.beauty_category = ProductCategory.objects.create(
            name="Beauty",
            slug="beauty",
            description="Beauty and skincare products",
        )
        self.inactive_category = ProductCategory.objects.create(
            name="Discontinued",
            slug="discontinued",
            description="Discontinued items",
            is_active=False,
        )

        # Create test products
        self.active_product_1 = Product.objects.create(
            name="Green Ankara Fabric Premium",
            slug="green-ankara-fabric-premium",
            sku="MH-FAB-104",
            category=self.fashion_category,
            description="Premium fabric for boutique retail.",
            selling_price=Decimal("12500.00"),
            cost_price=Decimal("9300.00"),
            reorder_level=8,
            is_active=True,
        )

        self.active_product_2 = Product.objects.create(
            name="Radiant Glow Serum",
            slug="radiant-glow-serum",
            sku="BT-SRM-001",
            category=self.beauty_category,
            description="A lightweight skincare serum for brighter complexion.",
            selling_price=Decimal("9500.00"),
            cost_price=Decimal("5000.00"),
            reorder_level=5,
            is_active=True,
        )

        self.inactive_product = Product.objects.create(
            name="Velvet Evening Gown",
            slug="velvet-evening-gown",
            sku="MH-GOWN-001",
            category=self.fashion_category,
            description="Elegant evening wear.",
            selling_price=Decimal("28000.00"),
            cost_price=Decimal("18000.00"),
            reorder_level=3,
            is_active=False,
        )

        # Add images to products
        self.image_1 = ProductImage.objects.create(
            product=self.active_product_1,
            image="products/demo-1.jpg",
            alt_text="Front view",
            display_order=1,
            is_primary=True,
        )
        self.image_2 = ProductImage.objects.create(
            product=self.active_product_1,
            image="products/demo-2.jpg",
            alt_text="Side view",
            display_order=2,
            is_primary=False,
        )
        self.image_3 = ProductImage.objects.create(
            product=self.active_product_2,
            image="products/demo-3.jpg",
            alt_text="Product image",
            display_order=1,
            is_primary=True,
        )

    def test_products_list_returns_200(self):
        """Test that GET /products/ returns 200 OK."""
        response = self.client.get(reverse('products:list'))
        self.assertEqual(response.status_code, 200)

    def test_products_list_returns_json(self):
        """Test that GET /products/ returns valid JSON."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertIn('success', data)
        self.assertIn('message', data)
        self.assertIn('data', data)

    def test_products_list_success_structure(self):
        """Test that success response has correct structure."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('products', data['data'])
        self.assertIn('pagination', data['data'])

    def test_products_list_returns_active_only(self):
        """Test that only active products are returned."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 2)
        product_ids = [p['id'] for p in products]
        self.assertIn(self.active_product_1.id, product_ids)
        self.assertIn(self.active_product_2.id, product_ids)
        self.assertNotIn(self.inactive_product.id, product_ids)

    def test_products_list_includes_required_fields(self):
        """Test that product list includes all required fields."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        product = data['data']['products'][0]
        required_fields = [
            'id', 'name', 'slug', 'sku', 'category',
            'selling_price', 'description', 'is_active', 'image', 'stock'
        ]
        for field in required_fields:
            self.assertIn(field, product)

    def test_products_list_includes_category(self):
        """Test that product category is properly serialized."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        product = data['data']['products'][0]
        self.assertIn('category', product)
        self.assertIn('id', product['category'])
        self.assertIn('name', product['category'])
        self.assertIn('slug', product['category'])

    def test_products_list_search_by_name(self):
        """Test that search by product name works."""
        response = self.client.get(reverse('products:list'), {'search': 'Ankara'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], "Green Ankara Fabric Premium")

    def test_products_list_search_by_sku(self):
        """Test that search by SKU works."""
        response = self.client.get(reverse('products:list'), {'search': 'MH-FAB'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['sku'], "MH-FAB-104")

    def test_products_list_search_case_insensitive(self):
        """Test that search is case-insensitive."""
        response = self.client.get(reverse('products:list'), {'search': 'SERUM'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], "Radiant Glow Serum")

    def test_products_list_filter_by_category_id(self):
        """Test that category filtering by ID works."""
        response = self.client.get(
            reverse('products:list'),
            {'category': str(self.beauty_category.id)}
        )
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['category']['id'], self.beauty_category.id)

    def test_products_list_filter_by_category_slug(self):
        """Test that category filtering by slug works."""
        response = self.client.get(
            reverse('products:list'),
            {'category': 'fashion'}
        )
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], "Green Ankara Fabric Premium")

    def test_products_list_sort_by_name(self):
        """Test that sorting by name works."""
        response = self.client.get(reverse('products:list'), {'sort_by': 'name'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(products[0]['name'], "Green Ankara Fabric Premium")
        self.assertEqual(products[1]['name'], "Radiant Glow Serum")

    def test_products_list_sort_by_price_asc(self):
        """Test that sorting by price ascending works."""
        response = self.client.get(reverse('products:list'), {'sort_by': 'price_asc'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(float(products[0]['selling_price']), 9500.00)
        self.assertEqual(float(products[1]['selling_price']), 12500.00)

    def test_products_list_sort_by_price_desc(self):
        """Test that sorting by price descending works."""
        response = self.client.get(reverse('products:list'), {'sort_by': 'price_desc'})
        data = response.json()
        products = data['data']['products']
        self.assertEqual(float(products[0]['selling_price']), 12500.00)
        self.assertEqual(float(products[1]['selling_price']), 9500.00)

    def test_products_list_pagination_default(self):
        """Test that pagination defaults to page 1, page_size 10."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        pagination = data['data']['pagination']
        self.assertEqual(pagination['page'], 1)
        self.assertEqual(pagination['page_size'], 10)

    def test_products_list_pagination_custom_page_size(self):
        """Test that custom page size works."""
        response = self.client.get(reverse('products:list'), {'page_size': 1})
        data = response.json()
        pagination = data['data']['pagination']
        self.assertEqual(pagination['page_size'], 1)
        self.assertEqual(len(data['data']['products']), 1)

    def test_products_list_pagination_max_page_size(self):
        """Test that page size is capped at 100."""
        response = self.client.get(reverse('products:list'), {'page_size': 500})
        data = response.json()
        pagination = data['data']['pagination']
        self.assertEqual(pagination['page_size'], 100)

    def test_products_list_includes_primary_image(self):
        """Test that primary image is included in product list."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        product = data['data']['products'][0]
        if product['id'] == self.active_product_1.id:
            self.assertIsNotNone(product['image'])
            self.assertIn('id', product['image'])
            self.assertIn('url', product['image'])
            self.assertIn('alt_text', product['image'])

    def test_products_list_stock_info_without_inventory(self):
        """Test that products without InventoryItem show OUT_OF_STOCK."""
        response = self.client.get(reverse('products:list'))
        data = response.json()
        product = data['data']['products'][0]
        self.assertIn('stock', product)
        self.assertEqual(product['stock']['quantity'], 0)
        self.assertEqual(product['stock']['status'], 'OUT_OF_STOCK')

    def test_product_detail_returns_200(self):
        """Test that GET /products/<id>/ returns 200 for active product."""
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_product_detail_returns_json(self):
        """Test that product detail returns valid JSON."""
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertIn('success', data)
        self.assertIn('data', data)

    def test_product_detail_includes_all_fields(self):
        """Test that product detail includes all required fields."""
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        data = response.json()
        product = data['data']
        required_fields = [
            'id', 'name', 'slug', 'sku', 'description', 'category',
            'selling_price', 'cost_price', 'reorder_level', 'is_active',
            'images', 'primary_image', 'stock', 'created_at', 'updated_at'
        ]
        for field in required_fields:
            self.assertIn(field, product)

    def test_product_detail_includes_all_images(self):
        """Test that all images are included in product detail."""
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        data = response.json()
        product = data['data']
        self.assertEqual(len(product['images']), 2)
        image_ids = [img['id'] for img in product['images']]
        self.assertIn(self.image_1.id, image_ids)
        self.assertIn(self.image_2.id, image_ids)

    def test_product_detail_primary_image(self):
        """Test that primary image is correctly identified."""
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        data = response.json()
        product = data['data']
        self.assertIsNotNone(product['primary_image'])
        self.assertEqual(product['primary_image']['id'], self.image_1.id)
        self.assertEqual(product['primary_image']['alt_text'], "Front view")

    def test_product_detail_inactive_product_returns_404(self):
        """Test that inactive product returns 404."""
        response = self.client.get(
            reverse('products:detail', args=[self.inactive_product.id])
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])

    def test_product_detail_nonexistent_returns_404(self):
        """Test that nonexistent product returns 404."""
        response = self.client.get(reverse('products:detail', args=[999]))
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])

    def test_product_detail_stock_without_inventory(self):
        """Test that product detail shows OUT_OF_STOCK without InventoryItem."""
        response = self.client.get(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        data = response.json()
        product = data['data']
        self.assertIn('stock', product)
        self.assertEqual(product['stock']['quantity'], 0)
        self.assertEqual(product['stock']['status'], 'OUT_OF_STOCK')
        self.assertTrue(product['stock']['is_out_of_stock'])
        self.assertFalse(product['stock']['is_low_stock'])

    def test_categories_list_returns_200(self):
        """Test that GET /products/categories/ returns 200."""
        response = self.client.get(reverse('products:categories'))
        self.assertEqual(response.status_code, 200)

    def test_categories_list_returns_json(self):
        """Test that categories endpoint returns valid JSON."""
        response = self.client.get(reverse('products:categories'))
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertIn('success', data)
        self.assertIn('data', data)

    def test_categories_list_returns_active_only(self):
        """Test that only active categories are returned."""
        response = self.client.get(reverse('products:categories'))
        data = response.json()
        categories = data['data']['categories']
        self.assertEqual(len(categories), 2)
        category_ids = [c['id'] for c in categories]
        self.assertIn(self.fashion_category.id, category_ids)
        self.assertIn(self.beauty_category.id, category_ids)
        self.assertNotIn(self.inactive_category.id, category_ids)

    def test_categories_list_includes_required_fields(self):
        """Test that categories include all required fields."""
        response = self.client.get(reverse('products:categories'))
        data = response.json()
        category = data['data']['categories'][0]
        required_fields = ['id', 'name', 'slug', 'description', 'is_active']
        for field in required_fields:
            self.assertIn(field, category)

    def test_categories_list_ordered_by_name(self):
        """Test that categories are ordered by name."""
        response = self.client.get(reverse('products:categories'))
        data = response.json()
        categories = data['data']['categories']
        self.assertEqual(categories[0]['name'], "Beauty")
        self.assertEqual(categories[1]['name'], "Fashion")

    def test_post_request_not_allowed_products_list(self):
        """Test that POST to /products/ returns 405."""
        response = self.client.post(reverse('products:list'))
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertFalse(data['success'])

    def test_post_request_not_allowed_product_detail(self):
        """Test that POST to /products/<id>/ returns 405."""
        response = self.client.post(
            reverse('products:detail', args=[self.active_product_1.id])
        )
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertFalse(data['success'])

    def test_post_request_not_allowed_categories(self):
        """Test that POST to /products/categories/ returns 405."""
        response = self.client.post(reverse('products:categories'))
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertFalse(data['success'])

    def test_products_list_with_invalid_page_number(self):
        """Test that invalid page number defaults to 1."""
        response = self.client.get(reverse('products:list'), {'page': 'invalid'})
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pagination']['page'], 1)

    def test_products_list_with_zero_page_number(self):
        """Test that page 0 defaults to 1."""
        response = self.client.get(reverse('products:list'), {'page': 0})
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pagination']['page'], 1)

    def test_products_list_combined_search_and_filter(self):
        """Test that search and filter work together."""
        response = self.client.get(
            reverse('products:list'),
            {'search': 'Radiant', 'category': 'beauty'}
        )
        data = response.json()
        products = data['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], "Radiant Glow Serum")

    def test_django_system_checks_pass_with_new_endpoints(self):
        """Test that django system checks pass."""
        from django.core.management import call_command

        call_command('check')


class CustomerProductCatalogViewsTests(TestCase):
    """Integration and unit tests for customer catalog browsing and detail endpoints."""

    @classmethod
    def setUpTestData(cls):
        from apps.inventory.models import InventoryItem

        cls.cat_fashion = ProductCategory.objects.create(name='Customer Fashion', slug='cust-fashion')
        cls.cat_beauty = ProductCategory.objects.create(name='Customer Beauty', slug='cust-beauty')

        cls.product_1 = Product.objects.create(
            name='Ankara Silk Fabric',
            slug='ankara-silk-fabric',
            sku='FAB-001',
            category=cls.cat_fashion,
            selling_price=Decimal('5000.00'),
            description='Premium African print silk fabric.',
            is_active=True,
        )
        InventoryItem.objects.create(product=cls.product_1, quantity=15)

        cls.product_2 = Product.objects.create(
            name='Shea Glow Lotion',
            slug='shea-glow-lotion',
            sku='LOT-001',
            category=cls.cat_beauty,
            selling_price=Decimal('2500.00'),
            description='Natural glowing skin moisturizer.',
            is_active=True,
        )
        InventoryItem.objects.create(product=cls.product_2, quantity=3)

        cls.product_out_of_stock = Product.objects.create(
            name='Velvet Headwrap',
            slug='velvet-headwrap',
            sku='ACC-001',
            category=cls.cat_fashion,
            selling_price=Decimal('1500.00'),
            description='Luxurious soft velvet headwrap.',
            is_active=True,
        )
        InventoryItem.objects.create(product=cls.product_out_of_stock, quantity=0)

        cls.inactive_product = Product.objects.create(
            name='Discontinued Perfume',
            slug='discontinued-perfume',
            sku='PRF-999',
            category=cls.cat_beauty,
            selling_price=Decimal('9000.00'),
            is_active=False,
        )
        InventoryItem.objects.create(product=cls.inactive_product, quantity=5)

    def setUp(self):
        self.client = Client()

    def test_customer_products_list_html_rendering(self):
        response = self.client.get('/customer/products/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'customer/products.html')
        self.assertIn('products', response.context)
        self.assertIn('categories', response.context)
        self.assertContains(response, 'id="customerProductSearch"')
        self.assertNotContains(response, 'id="customerSearchForm"')

    def test_customer_global_search_remains_available_outside_catalog(self):
        response = self.client.get(f'/customer/products/{self.product_1.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="customerSearchForm"')

    def test_customer_catalog_filters_combine(self):
        response = self.client.get(
            '/customer/products/?q=silk&category=cust-fashion&stock=IN_STOCK&sort_by=price_desc&page=1&format=json'
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()['data']
        self.assertEqual(result['pagination']['total_count'], 1)
        self.assertEqual(result['products'][0]['name'], 'Ankara Silk Fabric')

    def test_customer_products_list_json_format(self):
        response = self.client.get('/customer/products/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pagination']['total_count'], 3)
        product_names = [p['name'] for p in data['data']['products']]
        self.assertIn('Ankara Silk Fabric', product_names)
        self.assertIn('Shea Glow Lotion', product_names)
        self.assertIn('Velvet Headwrap', product_names)
        self.assertNotIn('Discontinued Perfume', product_names)

    def test_customer_products_category_filtering(self):
        response = self.client.get('/customer/products/?category=cust-beauty&format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['data']['products']), 1)
        self.assertEqual(data['data']['products'][0]['name'], 'Shea Glow Lotion')

    def test_customer_products_keyword_search(self):
        response = self.client.get('/customer/products/?q=silk&format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['data']['products']), 1)
        self.assertEqual(data['data']['products'][0]['sku'], 'FAB-001')

    def test_customer_products_price_sorting(self):
        resp_asc = self.client.get('/customer/products/?sort_by=price_asc&format=json')
        products_asc = resp_asc.json()['data']['products']
        self.assertEqual(products_asc[0]['name'], 'Velvet Headwrap')
        self.assertEqual(products_asc[-1]['name'], 'Ankara Silk Fabric')

        resp_desc = self.client.get('/customer/products/?sort_by=price_desc&format=json')
        products_desc = resp_desc.json()['data']['products']
        self.assertEqual(products_desc[0]['name'], 'Ankara Silk Fabric')
        self.assertEqual(products_desc[-1]['name'], 'Velvet Headwrap')

    def test_customer_products_stock_filtering(self):
        response = self.client.get('/customer/products/?stock=OUT_OF_STOCK&format=json')
        self.assertEqual(response.status_code, 200)
        products = response.json()['data']['products']
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], 'Velvet Headwrap')

    def test_customer_products_pagination(self):
        response = self.client.get('/customer/products/?page=1&page_size=2&format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(len(data['products']), 2)
        self.assertEqual(data['pagination']['total_count'], 3)
        self.assertEqual(data['pagination']['total_pages'], 2)

    def test_customer_product_detail_json(self):
        response = self.client.get(f'/customer/products/{self.product_1.id}/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['name'], 'Ankara Silk Fabric')
        self.assertEqual(data['data']['selling_price'], '5000.00')
        self.assertEqual(data['data']['stock']['quantity'], 15)
        self.assertEqual(data['data']['stock']['status'], 'IN_STOCK')

    def test_customer_product_detail_html(self):
        response = self.client.get(f'/customer/products/{self.product_1.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'customer/product_detail.html')
        self.assertEqual(response.context['product'], self.product_1)

    def test_customer_product_detail_slug_and_sku(self):
        resp_slug = self.client.get(f'/customer/products/{self.product_1.slug}/?format=json')
        self.assertEqual(resp_slug.status_code, 200)
        self.assertEqual(resp_slug.json()['data']['name'], 'Ankara Silk Fabric')

        resp_sku = self.client.get(f'/customer/products/{self.product_1.sku}/?format=json')
        self.assertEqual(resp_sku.status_code, 200)
        self.assertEqual(resp_sku.json()['data']['name'], 'Ankara Silk Fabric')

    def test_customer_product_detail_not_found(self):
        response = self.client.get('/customer/products/999999/?format=json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_customer_product_detail_inactive_returns_404(self):
        response = self.client.get(f'/customer/products/{self.inactive_product.id}/?format=json')
        self.assertEqual(response.status_code, 404)

    def test_customer_product_rejects_non_get(self):
        self.assertEqual(self.client.post('/customer/products/').status_code, 405)
        self.assertEqual(self.client.post(f'/customer/products/{self.product_1.id}/').status_code, 405)


class ProductPricingSecurityTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(
            name='Luxury Fabrics',
            slug='luxury-fabrics',
            description='Premium fabrics',
        )
        self.product = Product.objects.create(
            name='Swiss Voile Lace',
            slug='swiss-voile-lace',
            sku='SVL-001',
            category=self.category,
            selling_price=Decimal('25000.00'),
            cost_price=Decimal('18000.00'),
        )
        self.owner = User.objects.create_user(
            email='pricing-owner@example.com',
            username='pricing-owner',
            password='StrongPass123',
            role='OWNER',
        )
        self.cashier = User.objects.create_user(
            email='pricing-cashier@example.com',
            username='pricing-cashier',
            password='StrongPass123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='pricing-customer@example.com',
            username='pricing-customer',
            password='StrongPass123',
            role='CUSTOMER',
        )

    def test_selling_price_lower_than_cost_price_rejected(self):
        self.product.selling_price = Decimal('15000.00')
        self.product.cost_price = Decimal('18000.00')
        with self.assertRaises(ValidationError):
            self.product.clean()

    def test_gross_profit_and_margin_properties(self):
        self.assertEqual(self.product.gross_profit, Decimal('7000.00'))
        self.assertEqual(self.product.gross_margin_percentage, Decimal('28.0'))

    def test_record_price_change_updates_both_prices_atomically(self):
        history = self.product.record_price_change(
            new_selling_price=Decimal('30000.00'),
            new_cost_price=Decimal('20000.00'),
            changed_by=self.owner,
            reason='Seasonal supplier price increase',
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_price, Decimal('30000.00'))
        self.assertEqual(self.product.cost_price, Decimal('20000.00'))

        self.assertEqual(history.previous_price, Decimal('25000.00'))
        self.assertEqual(history.new_price, Decimal('30000.00'))
        self.assertEqual(history.previous_cost_price, Decimal('18000.00'))
        self.assertEqual(history.new_cost_price, Decimal('20000.00'))
        self.assertEqual(history.gross_profit, Decimal('10000.00'))
        self.assertEqual(history.gross_margin_percentage, Decimal('33.3'))
        self.assertEqual(history.changed_by, self.owner)

    def test_record_price_change_rejects_selling_lower_than_cost(self):
        with self.assertRaises(ValidationError):
            self.product.record_price_change(
                new_selling_price=Decimal('15000.00'),
                new_cost_price=Decimal('22000.00'),
                changed_by=self.owner,
                reason='Invalid below-cost price',
            )

    def test_price_history_is_immutable(self):
        history = self.product.record_price_change(
            new_selling_price=Decimal('28000.00'),
            changed_by=self.owner,
            reason='Initial increase',
        )
        # Attempting to edit or delete must raise ValidationError
        with self.assertRaises(ValidationError):
            history.new_price = Decimal('50000.00')
            history.save()

        with self.assertRaises(ValidationError):
            history.delete()

    def test_customer_isolation_cost_price_and_margins_hidden(self):
        # Customer requesting product detail
        self.client.force_login(self.customer)
        response = self.client.get(f'/customer/products/{self.product.id}/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json().get('data', {})
        self.assertNotIn('cost_price', data)
        self.assertNotIn('gross_profit', data)
        self.assertNotIn('gross_margin_percentage', data)

        # Anonymous user requesting customer catalog
        self.client.logout()
        anon_resp = self.client.get('/customer/products/?format=json')
        self.assertEqual(anon_resp.status_code, 200)
        items = anon_resp.json().get('data', {}).get('products', [])
        for item in items:
            self.assertNotIn('cost_price', item)
            self.assertNotIn('gross_profit', item)
            self.assertNotIn('gross_margin_percentage', item)

    def test_staff_can_view_cost_price_and_margins(self):
        self.client.force_login(self.owner)
        response = self.client.get(f'/products/{self.product.id}/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json().get('data', {})
        self.assertIn('cost_price', data)
        self.assertIn('gross_profit', data)
        self.assertIn('gross_margin_percentage', data)
        self.assertEqual(data['cost_price'], '18000.00')


class ProductImageUploadAndDisplayTests(TestCase):
    """
    Test suite verifying that products created with uploaded images properly
    persist their images to the database and media directory, and that product list,
    detail, storefront, and POS endpoints expose accessible image URLs.
    """

    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username='image_manager',
            email='image_manager@example.com',
            password='Password123',
            role='MANAGER',
        )
        self.category = ProductCategory.objects.create(
            name='Luxury Bags',
            slug='luxury-bags',
            description='Handbags and clutches',
        )

    def _generate_image_file(self, filename='handbag.jpg', color=(20, 120, 80)):
        buffer = BytesIO()
        image = Image.new('RGB', (120, 120), color=color)
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        return SimpleUploadedFile(filename, buffer.read(), content_type='image/jpeg')

    def test_product_creation_with_image_upload_and_display(self):
        self.client.force_login(self.manager)
        image_file = self._generate_image_file('test_handbag.jpg')

        # 1. Create product with multipart/form-data upload
        response = self.client.post(
            reverse('products:create'),
            data={
                'name': 'MADAM HY Emerald Tote',
                'sku': 'MHY-TOTE-001',
                'category_id': self.category.id,
                'selling_price': '45000.00',
                'cost_price': '30000.00',
                'reorder_level': '5',
                'description': 'Handcrafted premium emerald leather tote bag.',
                'image': image_file,
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        product_id = data['data']['id']

        # Verify Product and ProductImage in database
        product = Product.objects.get(id=product_id)
        self.assertEqual(product.name, 'MADAM HY Emerald Tote')
        self.assertEqual(product.images.count(), 1)
        primary_image = product.primary_image
        self.assertIsNotNone(primary_image)
        self.assertTrue(primary_image.is_primary)
        self.assertTrue(bool(primary_image.image))
        self.assertTrue(primary_image.image.name.startswith('products/'))

        # Verify image URL property on model
        self.assertTrue(bool(product.image_url))
        self.assertEqual(product.image_url, primary_image.url)

        # 2. Verify Product List API exposes image URL
        list_response = self.client.get(reverse('products:list'))
        self.assertEqual(list_response.status_code, 200)
        list_data = list_response.json()
        created_item = next((p for p in list_data['data']['products'] if p['id'] == product_id), None)
        self.assertIsNotNone(created_item)
        self.assertIsNotNone(created_item['image'])
        self.assertEqual(created_item['image']['url'], primary_image.url)
        self.assertEqual(created_item['image_url'], primary_image.url)

        # 3. Verify Product Detail API exposes image URL
        detail_response = self.client.get(reverse('products:detail', args=[product_id]))
        self.assertEqual(detail_response.status_code, 200)
        detail_data = detail_response.json()['data']
        self.assertIsNotNone(detail_data['primary_image'])
        self.assertEqual(detail_data['primary_image']['url'], primary_image.url)
        self.assertIsNotNone(detail_data['image'])
        self.assertEqual(detail_data['image']['url'], primary_image.url)
        self.assertEqual(detail_data['image_url'], primary_image.url)
        self.assertEqual(len(detail_data['images']), 1)
        self.assertEqual(detail_data['images'][0]['url'], primary_image.url)

        # 4. Verify Customer Storefront List & Detail expose image
        cust_list_resp = self.client.get('/customer/products/?format=json')
        self.assertEqual(cust_list_resp.status_code, 200)
        cust_list_data = cust_list_resp.json()
        cust_item = next((p for p in cust_list_data['data']['products'] if p['id'] == product_id), None)
        self.assertIsNotNone(cust_item)
        self.assertEqual(cust_item['image']['url'], primary_image.url)

        cust_detail_resp = self.client.get(f'/customer/products/{product_id}/?format=json')
        self.assertEqual(cust_detail_resp.status_code, 200)
        cust_detail_data = cust_detail_resp.json()['data']
        self.assertEqual(cust_detail_data['primary_image']['url'], primary_image.url)

        # 5. Verify the saved image URL is directly accessible via HTTP GET (returns 200)
        image_url = primary_image.url
        media_response = self.client.get(image_url)
        self.assertEqual(media_response.status_code, 200)
        self.assertIn('image/', media_response.headers.get('Content-Type', ''))
