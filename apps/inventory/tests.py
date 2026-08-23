from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.products.models import Product, ProductCategory
from .models import InventoryItem, StockMovement
from .services import adjust_inventory_stock


class InventoryModelsTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(
            name='Fashion',
            slug='fashion',
            description='Fashion products',
        )
        self.product = Product.objects.create(
            name='Green Ankara Fabric Premium',
            slug='green-ankara-fabric-premium',
            sku='MH-FAB-104',
            category=self.category,
            description='Premium fabric for boutique retail.',
            selling_price=Decimal('12500.00'),
            cost_price=Decimal('9300.00'),
            reorder_level=8,
        )
        self.inventory = InventoryItem.objects.create(
            product=self.product,
            quantity=10,
        )
        self.owner = User.objects.create_user(
            email='owner@example.com',
            username='owner',
            first_name='Owner',
            last_name='User',
            password='StrongPass123',
            role='OWNER',
        )

    def test_inventory_record_creation_works(self):
        self.assertEqual(self.inventory.product, self.product)
        self.assertEqual(self.inventory.quantity, 10)

    def test_inventory_record_is_unique_per_product(self):
        with self.assertRaises(IntegrityError):
            InventoryItem.objects.create(product=self.product, quantity=5)

    def test_stock_in_updates_quantity_and_history(self):
        adjust_inventory_stock(
            self.inventory,
            quantity_delta=8,
            reason='Restock',
            reference='PO-1001',
            created_by=self.owner,
            movement_type='STOCK_IN',
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 18)
        movement = StockMovement.objects.filter(product=self.product).latest('created_at')
        self.assertEqual(movement.quantity, 8)
        self.assertEqual(movement.previous_quantity, 10)
        self.assertEqual(movement.new_quantity, 18)
        self.assertEqual(movement.created_by, self.owner)

    def test_stock_out_updates_quantity_and_history(self):
        adjust_inventory_stock(
            self.inventory,
            quantity_delta=-3,
            reason='Sales',
            reference='OUT-203',
            created_by=self.owner,
            movement_type='STOCK_OUT',
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)
        movement = StockMovement.objects.filter(product=self.product).latest('created_at')
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(movement.previous_quantity, 10)
        self.assertEqual(movement.new_quantity, 7)

    def test_stock_adjustment_records_previous_and_resulting_quantity(self):
        adjust_inventory_stock(
            self.inventory,
            quantity_delta=5,
            reason='Cycle count correction',
            reference='ADJ-001',
            movement_type='ADJUSTMENT',
        )

        movement = StockMovement.objects.filter(product=self.product).latest('created_at')
        self.assertEqual(movement.previous_quantity, 10)
        self.assertEqual(movement.new_quantity, 15)
        self.assertEqual(movement.reason, 'Cycle count correction')

    def test_negative_stock_is_rejected(self):
        with self.assertRaises(ValidationError):
            adjust_inventory_stock(self.inventory, -21, movement_type='STOCK_OUT')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)

    def test_zero_quantity_move_is_rejected(self):
        with self.assertRaises(ValidationError):
            adjust_inventory_stock(self.inventory, 0, movement_type='ADJUSTMENT')

    def test_low_stock_detection_works(self):
        self.product.reorder_level = 12
        self.product.save(update_fields=['reorder_level'])
        self.inventory.quantity = 10
        self.inventory.save(update_fields=['quantity'])

        self.assertTrue(self.inventory.is_low_stock)
        self.assertEqual(self.inventory.stock_status, 'LOW_STOCK')

    def test_out_of_stock_detection_works(self):
        self.inventory.quantity = 0
        self.inventory.save(update_fields=['quantity'])

        self.assertTrue(self.inventory.is_out_of_stock)
        self.assertEqual(self.inventory.stock_status, 'OUT_OF_STOCK')

    def test_movement_history_exists_for_each_change(self):
        adjust_inventory_stock(self.inventory, 2, movement_type='STOCK_IN')
        adjust_inventory_stock(self.inventory, -1, movement_type='STOCK_OUT')

        self.assertEqual(self.inventory.movements.count(), 2)

    def test_created_by_relationship_is_preserved(self):
        adjust_inventory_stock(
            self.inventory,
            quantity_delta=4,
            created_by=self.owner,
            movement_type='STOCK_IN',
        )

        movement = self.inventory.movements.latest('created_at')
        self.assertEqual(movement.created_by, self.owner)

    def test_inventory_adjustment_is_atomic_when_invalid(self):
        before_count = StockMovement.objects.count()

        with self.assertRaises(ValidationError):
            adjust_inventory_stock(self.inventory, -999, movement_type='STOCK_OUT')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), before_count)

    def test_model_adjust_stock_delegates_to_service_for_compatibility(self):
        returned = self.inventory.adjust_stock(3, movement_type='STOCK_IN')

        self.inventory.refresh_from_db()
        self.assertIs(returned, self.inventory)
        self.assertEqual(self.inventory.quantity, 13)

    def test_stock_movement_metadata_is_preserved(self):
        adjust_inventory_stock(
            self.inventory,
            quantity_delta=6,
            reason='Supplier delivery',
            reference='PO-2026-0007',
            created_by=self.owner,
            movement_type=StockMovement.MovementType.STOCK_IN,
        )

        movement = self.inventory.movements.latest('created_at')
        self.assertEqual(movement.reason, 'Supplier delivery')
        self.assertEqual(movement.reference, 'PO-2026-0007')
        self.assertEqual(movement.created_by, self.owner)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.STOCK_IN)

    def test_stock_adjustment_rolls_back_if_movement_creation_fails(self):
        before_count = StockMovement.objects.count()

        with patch('apps.inventory.services.StockMovement.save', side_effect=RuntimeError('movement failure')):
            with self.assertRaises(RuntimeError):
                adjust_inventory_stock(self.inventory, 5, movement_type='STOCK_IN')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), before_count)

    def test_stock_adjustment_uses_locked_database_quantity_not_stale_instance(self):
        stale_inventory = InventoryItem.objects.get(pk=self.inventory.pk)

        adjust_inventory_stock(self.inventory, 5, movement_type='STOCK_IN')
        adjust_inventory_stock(stale_inventory, -3, movement_type='STOCK_OUT')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 12)
        latest_movement = self.inventory.movements.latest('created_at')
        self.assertEqual(latest_movement.previous_quantity, 15)
        self.assertEqual(latest_movement.new_quantity, 12)

    def test_django_system_checks_pass(self):
        from django.core.management import call_command

        call_command('check')


class InventoryReadOnlyApiTests(TestCase):
    def setUp(self):
        self.fashion_category = ProductCategory.objects.create(
            name='Fashion API',
            slug='fashion-api',
            description='Fashion products',
        )
        self.beauty_category = ProductCategory.objects.create(
            name='Beauty API',
            slug='beauty-api',
            description='Beauty products',
        )

        self.ankara = Product.objects.create(
            name='Green Ankara Fabric Premium',
            slug='green-ankara-fabric-api',
            sku='API-FAB-104',
            category=self.fashion_category,
            description='Premium fabric for boutique retail.',
            selling_price=Decimal('12500.00'),
            cost_price=Decimal('9300.00'),
            reorder_level=8,
        )
        self.serum = Product.objects.create(
            name='Radiant Glow Serum',
            slug='radiant-glow-serum-api',
            sku='API-SER-220',
            category=self.beauty_category,
            description='Skin care product.',
            selling_price=Decimal('9500.00'),
            cost_price=Decimal('5000.00'),
            reorder_level=5,
        )
        self.bag = Product.objects.create(
            name='Leather Tote Bag',
            slug='leather-tote-bag-api',
            sku='API-BAG-301',
            category=self.fashion_category,
            description='Classic tote bag.',
            selling_price=Decimal('30000.00'),
            cost_price=Decimal('21000.00'),
            reorder_level=3,
        )
        self.inactive_product = Product.objects.create(
            name='Inactive Inventory Product',
            slug='inactive-inventory-product-api',
            sku='API-INACTIVE-001',
            category=self.fashion_category,
            selling_price=Decimal('1000.00'),
            reorder_level=1,
            is_active=False,
        )

        self.ankara_inventory = InventoryItem.objects.create(product=self.ankara, quantity=20)
        self.serum_inventory = InventoryItem.objects.create(product=self.serum, quantity=3)
        self.bag_inventory = InventoryItem.objects.create(product=self.bag, quantity=0)
        self.inactive_product_inventory = InventoryItem.objects.create(
            product=self.inactive_product,
            quantity=99,
        )

        self.owner = User.objects.create_user(
            email='inventory-api-owner@example.com',
            username='inventory-api-owner',
            first_name='Inventory',
            last_name='Owner',
            password='StrongPass123',
            role='OWNER',
        )

        StockMovement.objects.create(
            inventory_item=self.ankara_inventory,
            product=self.ankara,
            movement_type=StockMovement.MovementType.STOCK_IN,
            quantity=10,
            previous_quantity=10,
            new_quantity=20,
            reason='Restock',
            reference='PO-API-001',
            created_by=self.owner,
        )
        StockMovement.objects.create(
            inventory_item=self.ankara_inventory,
            product=self.ankara,
            movement_type=StockMovement.MovementType.STOCK_OUT,
            quantity=-2,
            previous_quantity=20,
            new_quantity=18,
            reason='Sale',
            reference='SALE-API-001',
            created_by=self.owner,
        )

    def test_inventory_list_success(self):
        response = self.client.get(reverse('inventory:list'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'Inventory retrieved successfully.')
        self.assertIn('inventory', data['data'])
        self.assertIn('pagination', data['data'])
        self.assertEqual(len(data['data']['inventory']), 3)

    def test_inventory_list_response_format_and_fields(self):
        response = self.client.get(reverse('inventory:list'))

        data = response.json()
        item = data['data']['inventory'][0]
        for field in [
            'id',
            'product',
            'sku',
            'quantity',
            'reorder_level',
            'stock_status',
            'is_low_stock',
            'is_out_of_stock',
            'is_active',
        ]:
            self.assertIn(field, item)
        self.assertIn('category', item['product'])

    def test_inventory_list_searches_by_product_name(self):
        response = self.client.get(reverse('inventory:list'), {'search': 'Ankara'})

        items = response.json()['data']['inventory']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['product']['name'], 'Green Ankara Fabric Premium')

    def test_inventory_list_searches_by_sku(self):
        response = self.client.get(reverse('inventory:list'), {'search': 'SER-220'})

        items = response.json()['data']['inventory']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], 'API-SER-220')

    def test_inventory_list_filters_by_in_stock(self):
        response = self.client.get(reverse('inventory:list'), {'stock_status': 'IN_STOCK'})

        items = response.json()['data']['inventory']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.ankara_inventory.id)
        self.assertEqual(items[0]['stock_status'], 'IN_STOCK')

    def test_inventory_list_filters_by_low_stock(self):
        response = self.client.get(reverse('inventory:list'), {'stock_status': 'LOW_STOCK'})

        items = response.json()['data']['inventory']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.serum_inventory.id)
        self.assertTrue(items[0]['is_low_stock'])

    def test_inventory_list_filters_by_out_of_stock(self):
        response = self.client.get(reverse('inventory:list'), {'stock_status': 'OUT_OF_STOCK'})

        items = response.json()['data']['inventory']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.bag_inventory.id)
        self.assertTrue(items[0]['is_out_of_stock'])

    def test_inventory_list_sorts_by_quantity_desc(self):
        response = self.client.get(reverse('inventory:list'), {'sort_by': 'quantity_desc'})

        quantities = [item['quantity'] for item in response.json()['data']['inventory']]
        self.assertEqual(quantities, [20, 3, 0])

    def test_inventory_list_sorts_by_sku(self):
        response = self.client.get(reverse('inventory:list'), {'sort_by': 'sku'})

        skus = [item['sku'] for item in response.json()['data']['inventory']]
        self.assertEqual(skus, ['API-BAG-301', 'API-FAB-104', 'API-SER-220'])

    def test_inventory_list_pagination(self):
        response = self.client.get(reverse('inventory:list'), {'page_size': 2, 'page': 2})

        data = response.json()['data']
        self.assertEqual(data['pagination']['total_count'], 3)
        self.assertEqual(data['pagination']['page'], 2)
        self.assertEqual(data['pagination']['page_size'], 2)
        self.assertEqual(data['pagination']['total_pages'], 2)
        self.assertEqual(len(data['inventory']), 1)

    def test_inventory_list_invalid_pagination_defaults(self):
        response = self.client.get(reverse('inventory:list'), {'page': 'bad', 'page_size': 'bad'})

        pagination = response.json()['data']['pagination']
        self.assertEqual(pagination['page'], 1)
        self.assertEqual(pagination['page_size'], 10)

    def test_inventory_detail_success(self):
        response = self.client.get(reverse('inventory:detail', args=[self.ankara_inventory.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        item = data['data']
        self.assertEqual(item['id'], self.ankara_inventory.id)
        self.assertEqual(item['product']['id'], self.ankara.id)
        self.assertEqual(item['sku'], self.ankara.sku)
        self.assertEqual(item['quantity'], 20)
        self.assertEqual(item['reorder_level'], 8)
        self.assertEqual(item['stock_status'], 'IN_STOCK')
        self.assertIn('created_at', item)
        self.assertIn('updated_at', item)

    def test_inventory_detail_missing_returns_404(self):
        response = self.client.get(reverse('inventory:detail', args=[999999]))

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['message'], 'Inventory item not found.')

    def test_inventory_detail_excludes_inactive_product_inventory(self):
        response = self.client.get(reverse('inventory:detail', args=[self.inactive_product_inventory.id]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_inventory_movements_success(self):
        response = self.client.get(reverse('inventory:movements', args=[self.ankara_inventory.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('inventory', data['data'])
        self.assertIn('movements', data['data'])
        self.assertIn('pagination', data['data'])
        self.assertEqual(len(data['data']['movements']), 2)

    def test_inventory_movements_fields_and_metadata(self):
        response = self.client.get(reverse('inventory:movements', args=[self.ankara_inventory.id]))

        movement = response.json()['data']['movements'][0]
        for field in [
            'id',
            'movement_type',
            'quantity',
            'delta',
            'previous_quantity',
            'new_quantity',
            'reason',
            'reference',
            'created_by',
            'created_at',
        ]:
            self.assertIn(field, movement)
        self.assertEqual(movement['quantity'], movement['delta'])
        self.assertEqual(movement['created_by']['id'], self.owner.id)

    def test_inventory_movements_pagination(self):
        response = self.client.get(
            reverse('inventory:movements', args=[self.ankara_inventory.id]),
            {'page_size': 1},
        )

        data = response.json()['data']
        self.assertEqual(data['pagination']['total_count'], 2)
        self.assertEqual(data['pagination']['page_size'], 1)
        self.assertEqual(len(data['movements']), 1)

    def test_inventory_movements_missing_inventory_returns_404(self):
        response = self.client.get(reverse('inventory:movements', args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_inventory_endpoints_reject_write_methods(self):
        endpoints = [
            reverse('inventory:list'),
            reverse('inventory:detail', args=[self.ankara_inventory.id]),
            reverse('inventory:movements', args=[self.ankara_inventory.id]),
        ]

        for endpoint in endpoints:
            for method in [self.client.post, self.client.put, self.client.patch, self.client.delete]:
                response = method(endpoint, data={'quantity': 999}, content_type='application/json')
                self.assertEqual(response.status_code, 405)
                self.assertFalse(response.json()['success'])

        self.ankara_inventory.refresh_from_db()
        self.assertEqual(self.ankara_inventory.quantity, 20)
        self.assertEqual(StockMovement.objects.filter(inventory_item=self.ankara_inventory).count(), 2)

    def test_inventory_list_uses_constant_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('inventory:list'))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 2)

    def test_inventory_movements_uses_constant_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('inventory:movements', args=[self.ankara_inventory.id]))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 4)
