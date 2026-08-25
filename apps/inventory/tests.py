from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

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


class InventoryReportingApiTests(TestCase):
    def setUp(self):
        self.cat_fabrics = ProductCategory.objects.create(
            name='Luxury Fabrics',
            slug='luxury-fabrics',
            description='Textiles and lace materials',
        )
        self.cat_cosmetics = ProductCategory.objects.create(
            name='Cosmetics',
            slug='cosmetics',
            description='Skincare and cosmetics',
        )

        # Product 1: In Stock (qty=25, reorder=10)
        self.p1_fabric = Product.objects.create(
            name='Royal Lace Fabric',
            slug='royal-lace-fabric',
            sku='RPT-FAB-001',
            category=self.cat_fabrics,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('6000.00'),
            reorder_level=10,
        )
        self.inv1 = InventoryItem.objects.create(product=self.p1_fabric, quantity=25)

        # Product 2: Low Stock (qty=4, reorder=8 -> shortage = 4)
        self.p2_serum = Product.objects.create(
            name='Silk Face Serum',
            slug='silk-face-serum',
            sku='RPT-SER-002',
            category=self.cat_cosmetics,
            selling_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00'),
            reorder_level=8,
        )
        self.inv2 = InventoryItem.objects.create(product=self.p2_serum, quantity=4)

        # Product 3: Out of Stock (qty=0, reorder=5 -> shortage = 5)
        self.p3_perfume = Product.objects.create(
            name='Amber Oud Perfume',
            slug='amber-oud-perfume',
            sku='RPT-PER-003',
            category=self.cat_cosmetics,
            selling_price=Decimal('15000.00'),
            cost_price=Decimal('10000.00'),
            reorder_level=5,
        )
        self.inv3 = InventoryItem.objects.create(product=self.p3_perfume, quantity=0)

        # Product 4: Inactive Product (should be excluded from reporting summaries)
        self.p4_inactive = Product.objects.create(
            name='Discontinued Scent',
            slug='discontinued-scent',
            sku='RPT-DISC-004',
            category=self.cat_cosmetics,
            selling_price=Decimal('2000.00'),
            cost_price=Decimal('1000.00'),
            reorder_level=2,
            is_active=False,
        )
        self.inv4 = InventoryItem.objects.create(product=self.p4_inactive, quantity=50)

        # Users
        self.owner = User.objects.create_user(
            email='rpt_owner@example.com',
            username='rpt_owner',
            password='StrongPassword123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='rpt_manager@example.com',
            username='rpt_manager',
            password='StrongPassword123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='rpt_cashier@example.com',
            username='rpt_cashier',
            password='StrongPassword123',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            email='rpt_staff@example.com',
            username='rpt_staff',
            password='StrongPassword123',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            email='rpt_customer@example.com',
            username='rpt_customer',
            password='StrongPassword123',
            role='CUSTOMER',
        )

        # Create movements with distinct dates
        now = timezone.now()
        self.m1 = StockMovement.objects.create(
            inventory_item=self.inv1,
            product=self.p1_fabric,
            movement_type=StockMovement.MovementType.STOCK_IN,
            quantity=30,
            previous_quantity=0,
            new_quantity=30,
            reason='Initial stock receipt',
            reference='PO-2026-01',
            created_by=self.owner,
        )
        # Update created_at to 10 days ago
        StockMovement.objects.filter(pk=self.m1.pk).update(created_at=now - timedelta(days=10))

        self.m2 = StockMovement.objects.create(
            inventory_item=self.inv1,
            product=self.p1_fabric,
            movement_type=StockMovement.MovementType.STOCK_OUT,
            quantity=-5,
            previous_quantity=30,
            new_quantity=25,
            reason='Store customer sale',
            reference='SALE-2026-01',
            created_by=self.cashier,
        )
        StockMovement.objects.filter(pk=self.m2.pk).update(created_at=now - timedelta(days=5))

        self.m3 = StockMovement.objects.create(
            inventory_item=self.inv2,
            product=self.p2_serum,
            movement_type=StockMovement.MovementType.STOCK_IN,
            quantity=10,
            previous_quantity=0,
            new_quantity=10,
            reason='Batch restock',
            reference='PO-2026-02',
            created_by=self.manager,
        )
        StockMovement.objects.filter(pk=self.m3.pk).update(created_at=now - timedelta(days=3))

        self.m4 = StockMovement.objects.create(
            inventory_item=self.inv2,
            product=self.p2_serum,
            movement_type=StockMovement.MovementType.STOCK_OUT,
            quantity=-6,
            previous_quantity=10,
            new_quantity=4,
            reason='Online store orders',
            reference='SALE-2026-02',
            created_by=self.staff,
        )
        StockMovement.objects.filter(pk=self.m4.pk).update(created_at=now - timedelta(days=1))

    # --- Authentication & Authorization Tests ---

    def test_reporting_endpoints_require_authentication(self):
        endpoints = [
            reverse('inventory:reports_summary'),
            reverse('inventory:reports_movements'),
            reverse('inventory:reports_low_stock'),
        ]
        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 401, f'Expected 401 for unauthenticated {url}')
            data = response.json()
            self.assertFalse(data['success'])
            self.assertEqual(data['message'], 'Authentication required.')

    def test_customer_role_is_forbidden_from_reports(self):
        self.client.force_login(self.customer)
        endpoints = [
            reverse('inventory:reports_summary'),
            reverse('inventory:reports_movements'),
            reverse('inventory:reports_low_stock'),
        ]
        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, f'Expected 403 for customer on {url}')
            data = response.json()
            self.assertFalse(data['success'])
            self.assertIn('permission', data['message'].lower())

    def test_staff_roles_are_authorized_to_access_reports(self):
        staff_users = [self.owner, self.manager, self.cashier, self.staff]
        endpoints = [
            reverse('inventory:reports_summary'),
            reverse('inventory:reports_movements'),
            reverse('inventory:reports_low_stock'),
        ]
        for user in staff_users:
            self.client.force_login(user)
            for url in endpoints:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, f'Expected 200 for {user.role} on {url}')
                self.assertTrue(response.json()['success'])

    # --- Summary Endpoint Tests ---

    def test_summary_report_calculations(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_summary'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        summary = data['data']

        # 3 active inventory items (p1, p2, p3) - inactive p4 excluded
        self.assertEqual(summary['total_items'], 3)
        self.assertEqual(summary['active_items'], 3)
        # Units: p1 (25) + p2 (4) + p3 (0) = 29
        self.assertEqual(summary['total_units'], 29)
        # Low stock: p2 (qty=4 <= reorder 8, qty > 0) = 1
        self.assertEqual(summary['low_stock_items'], 1)
        # Out of stock: p3 (qty=0) = 1
        self.assertEqual(summary['out_of_stock_items'], 1)
        # In stock: p1 (qty=25 > reorder 10) = 1
        self.assertEqual(summary['in_stock_items'], 1)

        # Values:
        # Selling: (25 * 10000) + (4 * 5000) + (0 * 15000) = 250000 + 20000 = 270000.00
        # Cost: (25 * 6000) + (4 * 3000) + (0 * 10000) = 150000 + 12000 = 162000.00
        self.assertEqual(Decimal(summary['selling_value']), Decimal('270000.00'))
        self.assertEqual(Decimal(summary['cost_value']), Decimal('162000.00'))
        self.assertEqual(Decimal(summary['inventory_value']), Decimal('270000.00'))
        self.assertEqual(Decimal(summary['total_inventory_value']), Decimal('162000.00'))

    def test_summary_report_empty_inventory(self):
        InventoryItem.objects.all().delete()
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_summary'))

        self.assertEqual(response.status_code, 200)
        summary = response.json()['data']
        self.assertEqual(summary['total_items'], 0)
        self.assertEqual(summary['total_units'], 0)
        self.assertEqual(summary['low_stock_items'], 0)
        self.assertEqual(summary['out_of_stock_items'], 0)
        self.assertEqual(Decimal(summary['cost_value']), Decimal('0.00'))
        self.assertEqual(Decimal(summary['selling_value']), Decimal('0.00'))

    # --- Low-Stock Report Tests ---

    def test_low_stock_report_fields_and_shortages(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_low_stock'))

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']

        self.assertEqual(data['total_low_stock'], 2)
        self.assertEqual(data['critical_count'], 1)  # p3 (out of stock)
        self.assertEqual(data['warning_count'], 1)   # p2 (low stock)

        items = data['low_stock_products']
        self.assertEqual(len(items), 2)

        # First item should be critical (qty=0)
        p3_item = next(i for i in items if i['id'] == self.inv3.id)
        self.assertEqual(p3_item['quantity'], 0)
        self.assertEqual(p3_item['reorder_level'], 5)
        self.assertEqual(p3_item['shortage_amount'], 5)
        self.assertEqual(p3_item['stock_status'], 'OUT_OF_STOCK')
        self.assertEqual(p3_item['urgency'], 'CRITICAL')
        self.assertTrue(p3_item['is_out_of_stock'])

        # Second item should be warning (qty=4)
        p2_item = next(i for i in items if i['id'] == self.inv2.id)
        self.assertEqual(p2_item['quantity'], 4)
        self.assertEqual(p2_item['reorder_level'], 8)
        self.assertEqual(p2_item['shortage_amount'], 4)
        self.assertEqual(p2_item['stock_status'], 'LOW_STOCK')
        self.assertEqual(p2_item['urgency'], 'WARNING')
        self.assertTrue(p2_item['is_low_stock'])

    def test_low_stock_report_search_and_filters(self):
        self.client.force_login(self.owner)

        # Search by product name
        res_search = self.client.get(reverse('inventory:reports_low_stock'), {'search': 'Serum'})
        items = res_search.json()['data']['low_stock_products']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], self.inv2.id)

        # Filter by status OUT_OF_STOCK / CRITICAL
        res_crit = self.client.get(reverse('inventory:reports_low_stock'), {'status': 'CRITICAL'})
        items_crit = res_crit.json()['data']['low_stock_products']
        self.assertEqual(len(items_crit), 1)
        self.assertEqual(items_crit[0]['id'], self.inv3.id)

        # Filter by status LOW_STOCK / WARNING
        res_warn = self.client.get(reverse('inventory:reports_low_stock'), {'status': 'LOW_STOCK'})
        items_warn = res_warn.json()['data']['low_stock_products']
        self.assertEqual(len(items_warn), 1)
        self.assertEqual(items_warn[0]['id'], self.inv2.id)

    def test_low_stock_report_pagination(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_low_stock'), {'page_size': 1, 'page': 1})

        data = response.json()['data']
        self.assertEqual(data['pagination']['total_count'], 2)
        self.assertEqual(data['pagination']['page_size'], 1)
        self.assertEqual(data['pagination']['total_pages'], 2)
        self.assertEqual(len(data['low_stock_products']), 1)

    # --- Movements Report Tests ---

    def test_movements_report_aggregations(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_movements'))

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']

        # Total movements: 4
        self.assertEqual(data['summary']['total_movements'], 4)
        # Stock In: m1 (+30) + m3 (+10) = 40
        self.assertEqual(data['stock_in_quantity'], 40)
        self.assertEqual(data['summary']['stock_in_quantity'], 40)
        # Stock Out: m2 (-5) + m4 (-6) = 11 units out
        self.assertEqual(data['stock_out_quantity'], 11)
        self.assertEqual(data['summary']['stock_out_quantity'], 11)
        # Net Movement: +40 - 11 = +29
        self.assertEqual(data['net_movement'], 29)
        self.assertEqual(data['summary']['net_movement'], 29)

        # Movement counts breakdown by type
        counts = data['movement_counts']
        self.assertEqual(counts.get('STOCK_IN'), 2)
        self.assertEqual(counts.get('STOCK_OUT'), 2)

    def test_movements_report_date_filtering(self):
        self.client.force_login(self.owner)
        now = timezone.localdate()

        date_from = (now - timedelta(days=6)).isoformat()
        date_to = now.isoformat()

        response = self.client.get(reverse('inventory:reports_movements'), {
            'date_from': date_from,
            'date_to': date_to,
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']

        # Movements in last 6 days: m2 (5 days ago, -5), m3 (3 days ago, +10), m4 (1 day ago, -6)
        # Excludes m1 (10 days ago, +30)
        self.assertEqual(data['summary']['total_movements'], 3)
        self.assertEqual(data['stock_in_quantity'], 10)
        self.assertEqual(data['stock_out_quantity'], 11)
        self.assertEqual(data['net_movement'], -1)

    def test_movements_report_invalid_date_formats(self):
        self.client.force_login(self.owner)

        # Malformed date_from
        res1 = self.client.get(reverse('inventory:reports_movements'), {'date_from': 'invalid-date'})
        self.assertEqual(res1.status_code, 400)
        self.assertFalse(res1.json()['success'])
        self.assertIn('date_from', res1.json()['errors'])

        # Malformed date_to
        res2 = self.client.get(reverse('inventory:reports_movements'), {'date_to': '2026-13-45'})
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.json()['success'])
        self.assertIn('date_to', res2.json()['errors'])

        # date_from > date_to
        res3 = self.client.get(reverse('inventory:reports_movements'), {
            'date_from': '2026-08-25',
            'date_to': '2026-08-20',
        })
        self.assertEqual(res3.status_code, 400)
        self.assertFalse(res3.json()['success'])
        self.assertIn('date_from', res3.json()['errors'])

    def test_movements_report_type_and_product_filters(self):
        self.client.force_login(self.owner)

        # Filter by STOCK_IN only
        res_type = self.client.get(reverse('inventory:reports_movements'), {'movement_type': 'STOCK_IN'})
        data_type = res_type.json()['data']
        self.assertEqual(data_type['summary']['total_movements'], 2)
        self.assertEqual(data_type['stock_in_quantity'], 40)
        self.assertEqual(data_type['stock_out_quantity'], 0)

        # Filter by product_id
        res_prod = self.client.get(reverse('inventory:reports_movements'), {'product_id': self.p1_fabric.id})
        data_prod = res_prod.json()['data']
        self.assertEqual(data_prod['summary']['total_movements'], 2)
        self.assertEqual(data_prod['stock_in_quantity'], 30)
        self.assertEqual(data_prod['stock_out_quantity'], 5)
        self.assertEqual(data_prod['net_movement'], 25)

    def test_movements_report_pagination(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_movements'), {'page_size': 2, 'page': 1})

        data = response.json()['data']
        self.assertEqual(data['pagination']['total_count'], 4)
        self.assertEqual(data['pagination']['page_size'], 2)
        self.assertEqual(data['pagination']['total_pages'], 2)
        self.assertEqual(len(data['movements']), 2)

    def test_movements_report_empty_range(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('inventory:reports_movements'), {
            'date_from': '2020-01-01',
            'date_to': '2020-01-02',
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['summary']['total_movements'], 0)
        self.assertEqual(data['stock_in_quantity'], 0)
        self.assertEqual(data['stock_out_quantity'], 0)
        self.assertEqual(data['net_movement'], 0)
        self.assertEqual(len(data['movements']), 0)

    # --- HTTP Methods Restriction Tests ---

    def test_reporting_endpoints_reject_write_methods(self):
        self.client.force_login(self.owner)
        endpoints = [
            reverse('inventory:reports_summary'),
            reverse('inventory:reports_movements'),
            reverse('inventory:reports_low_stock'),
        ]
        for url in endpoints:
            for method in [self.client.post, self.client.put, self.client.patch, self.client.delete]:
                response = method(url, data={'test': 123}, content_type='application/json')
                self.assertEqual(response.status_code, 405, f'Expected 405 for {method.__name__} on {url}')
                self.assertFalse(response.json()['success'])

    # --- Query Optimization / No N+1 Tests ---

    def test_summary_report_uses_bounded_queries(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('inventory:reports_summary'))

        self.assertEqual(response.status_code, 200)
        # Summary calculation runs in 1 aggregate query (+ session/auth query)
        self.assertLessEqual(len(queries), 3)

    def test_movements_report_uses_bounded_queries(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('inventory:reports_movements'))

        self.assertEqual(response.status_code, 200)
        # Aggregation + type counts + paginated movements + auth
        self.assertLessEqual(len(queries), 5)

    def test_low_stock_report_uses_bounded_queries(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('inventory:reports_low_stock'))

        self.assertEqual(response.status_code, 200)
        # Aggregation + paginated select_related + auth
        self.assertLessEqual(len(queries), 4)


class InventoryAdjustmentApiTests(TestCase):
    def setUp(self):
        category = ProductCategory.objects.create(name='Adjustment API', slug='adjustment-api')
        product = Product.objects.create(
            name='Adjustment Product',
            slug='adjustment-product',
            sku='ADJ-001',
            category=category,
            selling_price=Decimal('100.00'),
        )
        self.inventory = InventoryItem.objects.create(product=product, quantity=10)
        self.owner = User.objects.create_user(
            email='adjust-owner@example.com', username='adjust-owner', password='StrongPass123', role='OWNER'
        )
        self.manager = User.objects.create_user(
            email='adjust-manager@example.com', username='adjust-manager', password='StrongPass123', role='MANAGER'
        )
        self.customer = User.objects.create_user(
            email='adjust-customer@example.com', username='adjust-customer', password='StrongPass123', role='CUSTOMER'
        )

    def adjustment_url(self):
        return reverse('inventory:adjust', args=[self.inventory.id])

    def test_adjustment_updates_inventory_and_returns_movement(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            self.adjustment_url(),
            data={'delta': 5, 'reason': 'New stock received', 'reference': 'PO-001'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['previous_quantity'], 10)
        self.assertEqual(data['new_quantity'], 15)
        self.assertEqual(data['delta'], 5)
        self.assertEqual(data['reason'], 'New stock received')
        self.assertEqual(data['reference'], 'PO-001')
        self.assertEqual(data['movement']['new_quantity'], 15)

    def test_adjustment_rejects_invalid_delta(self):
        self.client.force_login(self.owner)
        for payload in ({'reason': 'Missing delta'}, {'delta': 0, 'reason': 'Zero'}, {'delta': 'abc', 'reason': 'Bad'}):
            response = self.client.post(self.adjustment_url(), data=payload, content_type='application/json')
            self.assertEqual(response.status_code, 400)

    def test_adjustment_authorization_and_method_errors(self):
        unauthenticated = self.client.post(self.adjustment_url(), data={}, content_type='application/json')
        self.assertEqual(unauthenticated.status_code, 401)

        self.client.force_login(self.customer)
        forbidden = self.client.post(self.adjustment_url(), data={'delta': 1}, content_type='application/json')
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.manager)
        method_error = self.client.get(self.adjustment_url())
        self.assertEqual(method_error.status_code, 405)

    def test_adjustment_missing_item_returns_404(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('inventory:adjust', args=[999999]),
            data={'delta': 1},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
