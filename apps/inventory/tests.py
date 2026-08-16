from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User
from apps.products.models import Product, ProductCategory
from .models import InventoryItem, StockMovement


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
        self.inventory.adjust_stock(
            8,
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
        self.inventory.adjust_stock(
            -3,
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
        self.inventory.adjust_stock(
            5,
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
            self.inventory.adjust_stock(-21, movement_type='STOCK_OUT')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)

    def test_zero_quantity_move_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.inventory.adjust_stock(0, movement_type='ADJUSTMENT')

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
        self.inventory.adjust_stock(2, movement_type='STOCK_IN')
        self.inventory.adjust_stock(-1, movement_type='STOCK_OUT')

        self.assertEqual(self.inventory.movements.count(), 2)

    def test_created_by_relationship_is_preserved(self):
        self.inventory.adjust_stock(
            4,
            created_by=self.owner,
            movement_type='STOCK_IN',
        )

        movement = self.inventory.movements.latest('created_at')
        self.assertEqual(movement.created_by, self.owner)

    def test_inventory_adjustment_is_atomic_when_invalid(self):
        before_count = StockMovement.objects.count()

        with self.assertRaises(ValidationError):
            self.inventory.adjust_stock(-999, movement_type='STOCK_OUT')

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), before_count)

    def test_django_system_checks_pass(self):
        from django.core.management import call_command

        call_command('check')
