from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
import json

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


class ProductsAPITests(TestCase):
    """Test suite for Products read-only API endpoints."""

    def setUp(self):
        self.client = Client()

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
