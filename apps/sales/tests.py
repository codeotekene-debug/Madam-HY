import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.credits.models import CreditAccount, CreditTransaction
from apps.expenses.models import Expense
from apps.inventory.models import InventoryItem, StockMovement
from apps.orders.models import Order
from apps.products.models import Product, ProductCategory
from apps.requests.models import Request
from .models import Sale, SaleItem


class SaleModelTests(TestCase):
    """Tests for Sale model."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a category
        self.category = ProductCategory.objects.create(
            name='Fashion',
            slug='fashion',
            description='Fashion products',
        )

        # Create products with inventory
        self.product1 = Product.objects.create(
            name='Green Ankara Fabric Premium',
            slug='green-ankara-fabric-premium',
            sku='MH-FAB-104',
            category=self.category,
            description='Premium fabric for boutique retail.',
            selling_price=Decimal('12500.00'),
            cost_price=Decimal('9300.00'),
            reorder_level=8,
        )
        self.inventory1 = InventoryItem.objects.create(
            product=self.product1,
            quantity=20,
        )

        self.product2 = Product.objects.create(
            name='Velvet Evening Gown',
            slug='velvet-evening-gown',
            sku='MH-GOW-22',
            category=self.category,
            description='Elegant evening gown.',
            selling_price=Decimal('28000.00'),
            cost_price=Decimal('18000.00'),
            reorder_level=5,
        )
        self.inventory2 = InventoryItem.objects.create(
            product=self.product2,
            quantity=5,
        )

        # Create users
        self.cashier = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            first_name='Amina',
            last_name='Yusuf',
            password='StrongPass123',
            role='CASHIER',
        )

        self.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            first_name='John',
            last_name='Doe',
            password='StrongPass123',
            role='CUSTOMER',
        )

        self.owner = User.objects.create_user(
            email='owner@example.com',
            username='owner',
            first_name='Owner',
            last_name='User',
            password='StrongPass123',
            role='OWNER',
        )

    def test_sale_creation_with_cash(self):
        """Test creating a draft sale with cash payment."""
        sale = Sale.objects.create(
            sale_number='MH-001001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.assertEqual(sale.payment_method, Sale.PaymentMethod.CASH)
        self.assertIsNone(sale.customer)

    def test_sale_creation_with_customer(self):
        """Test creating a sale with a customer."""
        sale = Sale.objects.create(
            sale_number='MH-001002',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )
        self.assertEqual(sale.customer, self.customer)

    def test_sale_number_is_unique(self):
        """Test that sale numbers are unique."""
        Sale.objects.create(
            sale_number='MH-UNIQUE-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )
        with self.assertRaises(ValidationError):
            Sale.objects.create(
                sale_number='MH-UNIQUE-001',
                cashier=self.cashier,
                payment_method=Sale.PaymentMethod.CASH,
            )

    def test_credit_sale_requires_customer(self):
        """Test that credit sales require a customer."""
        sale = Sale(
            sale_number='MH-CREDIT-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            status=Sale.SaleStatus.DRAFT,
        )
        with self.assertRaises(ValidationError) as cm:
            sale.full_clean()
        self.assertIn('customer', cm.exception.error_dict)

    def test_credit_sale_with_non_customer_user_fails(self):
        """Test that credit sales with non-customer users fail."""
        sale = Sale(
            sale_number='MH-CREDIT-002',
            customer=self.cashier,  # Cashier is not a customer
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
        )
        with self.assertRaises(ValidationError) as cm:
            sale.full_clean()
        self.assertIn('customer', cm.exception.error_dict)

    def test_credit_sale_with_customer_succeeds(self):
        """Test that credit sales with customer user pass validation."""
        sale = Sale(
            sale_number='MH-CREDIT-003',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
        )
        sale.full_clean()  # Should not raise
        sale.save()
        self.assertEqual(sale.customer.role, 'CUSTOMER')

    def test_only_staff_can_be_cashier(self):
        """Test that only staff roles can process sales."""
        customer_cashier = Sale(
            sale_number='MH-BAD-CASHIER',
            cashier=self.customer,
            payment_method=Sale.PaymentMethod.CASH,
        )
        with self.assertRaises(ValidationError):
            customer_cashier.full_clean()

    def test_owner_can_process_sale(self):
        """Test that OWNER role can process sales as cashier."""
        sale = Sale(
            sale_number='MH-OWNER-001',
            cashier=self.owner,
            payment_method=Sale.PaymentMethod.CASH,
        )
        sale.full_clean()  # Should not raise
        sale.save()

    def test_calculate_totals_from_items(self):
        """Test that calculate_totals correctly sums SaleItems."""
        sale = Sale.objects.create(
            sale_number='MH-TOTALS-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product1,
            quantity=2,
            unit_price=Decimal('12500.00'),
            product_name_snapshot='Product 1',
            sku_snapshot='SKU-1',
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product2,
            quantity=1,
            unit_price=Decimal('28000.00'),
            product_name_snapshot='Product 2',
            sku_snapshot='SKU-2',
        )
        sale.calculate_totals()
        # subtotal = (2 * 12500) + (1 * 28000) = 25000 + 28000 = 53000
        self.assertEqual(sale.subtotal, Decimal('53000.00'))
        self.assertEqual(sale.total, Decimal('53000.00'))

    def test_calculate_totals_with_discount(self):
        """Test that calculate_totals applies discount correctly."""
        sale = Sale.objects.create(
            sale_number='MH-DISCOUNT-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            discount=Decimal('5000.00'),
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product1,
            quantity=2,
            unit_price=Decimal('12500.00'),
            product_name_snapshot='Product 1',
            sku_snapshot='SKU-1',
        )
        sale.calculate_totals()
        # subtotal = 25000, discount = 5000, total = 20000
        self.assertEqual(sale.subtotal, Decimal('25000.00'))
        self.assertEqual(sale.total, Decimal('20000.00'))

    def test_negative_amounts_fail_validation(self):
        """Test that negative monetary amounts fail validation."""
        sale = Sale(
            sale_number='MH-NEG-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            subtotal=Decimal('-100.00'),
        )
        with self.assertRaises(ValidationError):
            sale.full_clean()

        sale = Sale(
            sale_number='MH-NEG-002',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            discount=Decimal('-100.00'),
        )
        with self.assertRaises(ValidationError):
            sale.full_clean()


class SaleCompletionTests(TestCase):
    """Tests for completing sales and inventory deduction."""

    def setUp(self):
        """Set up test fixtures."""
        self.category = ProductCategory.objects.create(
            name='Test',
            slug='test',
        )
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            sku='TEST-001',
            category=self.category,
            selling_price=Decimal('1000.00'),
        )
        self.inventory = InventoryItem.objects.create(
            product=self.product,
            quantity=10,
        )
        self.cashier = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            password='Pass123',
            role='CASHIER',
        )

    def test_cannot_complete_sale_without_items(self):
        """Test that sales without items cannot be completed."""
        sale = Sale.objects.create(
            sale_number='MH-NO-ITEMS',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            sale.complete_sale()

    def test_cannot_complete_already_completed_sale(self):
        """Test that completed sales cannot be completed again."""
        sale = Sale.objects.create(
            sale_number='MH-ALREADY-DONE',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.COMPLETED,
        )
        with self.assertRaises(ValidationError):
            sale.complete_sale()

    def test_insufficient_stock_prevents_completion(self):
        """Test that sales fail when inventory is insufficient."""
        sale = Sale.objects.create(
            sale_number='MH-INSUFFICIENT',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=20,  # More than available (10)
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        with self.assertRaises(ValidationError):
            sale.complete_sale()

        # Inventory should remain unchanged
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)

    def test_successful_completion_deducts_inventory(self):
        """Test that completing a sale deducts inventory."""
        sale = Sale.objects.create(
            sale_number='MH-SUCCESS-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=3,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        sale.complete_sale()

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)

    def test_sale_completion_uses_inventory_service_not_model_adjust_stock(self):
        """Test sale stock deductions use the inventory service path."""
        sale = Sale.objects.create(
            sale_number='MH-SERVICE-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=4,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )

        with patch('apps.inventory.models.InventoryItem.adjust_stock', side_effect=AssertionError('wrong path')):
            sale.complete_sale()

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 6)
        movement = StockMovement.objects.get(reference=sale.sale_number)
        self.assertEqual(movement.quantity, -4)
        self.assertEqual(movement.previous_quantity, 10)
        self.assertEqual(movement.new_quantity, 6)

    def test_stock_movement_created_on_completion(self):
        """Test that StockMovement records are created when sale completes."""
        sale = Sale.objects.create(
            sale_number='MH-MOVEMENT-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        sale.complete_sale()

        # Verify StockMovement was created
        movement = StockMovement.objects.get(reference=sale.sale_number)
        self.assertEqual(movement.movement_type, 'STOCK_OUT')
        self.assertEqual(movement.quantity, -2)
        self.assertEqual(movement.previous_quantity, 10)
        self.assertEqual(movement.new_quantity, 8)
        self.assertEqual(movement.created_by, self.cashier)

    def test_multiple_items_deducted_atomically(self):
        """Test that multi-item sales deduct all inventory atomically."""
        product2 = Product.objects.create(
            name='Product 2',
            slug='product-2',
            sku='TEST-002',
            category=self.category,
            selling_price=Decimal('500.00'),
        )
        inventory2 = InventoryItem.objects.create(
            product=product2,
            quantity=5,
        )

        sale = Sale.objects.create(
            sale_number='MH-MULTI-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        SaleItem.objects.create(
            sale=sale,
            product=product2,
            quantity=3,
            unit_price=Decimal('500.00'),
            product_name_snapshot=product2.name,
            sku_snapshot=product2.sku,
        )

        sale.complete_sale()

        self.inventory.refresh_from_db()
        inventory2.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 8)
        self.assertEqual(inventory2.quantity, 2)

    def test_failed_inventory_deduction_rolls_back(self):
        """Test that failed inventory deduction causes complete transaction rollback."""
        product2 = Product.objects.create(
            name='Product 2',
            slug='product-2',
            sku='TEST-003',
            category=self.category,
            selling_price=Decimal('500.00'),
        )
        inventory2 = InventoryItem.objects.create(
            product=product2,
            quantity=2,  # Insufficient for the sale
        )

        sale = Sale.objects.create(
            sale_number='MH-ROLLBACK-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        # First item succeeds
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        # Second item fails (requesting 5 but only 2 available)
        SaleItem.objects.create(
            sale=sale,
            product=product2,
            quantity=5,
            unit_price=Decimal('500.00'),
            product_name_snapshot=product2.name,
            sku_snapshot=product2.sku,
        )

        with self.assertRaises(ValidationError):
            sale.complete_sale()

        # Verify rollback: both inventories should be unchanged
        self.inventory.refresh_from_db()
        inventory2.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(inventory2.quantity, 2)

        # Sale should still be DRAFT
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)

    def test_draft_sale_does_not_deduct_inventory(self):
        """Test that DRAFT sales do not affect inventory even if items exist."""
        sale = Sale.objects.create(
            sale_number='MH-DRAFT-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.DRAFT,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=5,
            unit_price=Decimal('1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )

        # Draft sale is not completed, so no movement
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.filter(reference=sale.sale_number).count(), 0)


class SaleItemModelTests(TestCase):
    """Tests for SaleItem model."""

    def setUp(self):
        """Set up test fixtures."""
        self.category = ProductCategory.objects.create(
            name='Test',
            slug='test',
        )
        self.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            sku='TEST-001',
            category=self.category,
            selling_price=Decimal('1000.00'),
        )
        self.cashier = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            password='Pass123',
            role='CASHIER',
        )
        self.sale = Sale.objects.create(
            sale_number='MH-TEST-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )

    def test_sale_item_creation(self):
        """Test creating a sale item."""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('1000.00'),
            product_name_snapshot='Test Product',
            sku_snapshot='TEST-001',
        )
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal('1000.00'))

    def test_sale_item_price_snapshot_preserved_after_product_change(self):
        """Test that SaleItem price remains correct if Product price changes later."""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=1,
            unit_price=Decimal('1000.00'),
            product_name_snapshot='Original Name',
            sku_snapshot='TEST-001',
        )
        # Change product price and name
        self.product.selling_price = Decimal('2000.00')
        self.product.name = 'New Name'
        self.product.save()

        # SaleItem should retain the historical values
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal('1000.00'))
        self.assertEqual(item.product_name_snapshot, 'Original Name')

    def test_line_total_calculation(self):
        """Test line_total calculation (quantity × unit_price - discount)."""
        item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=5,
            unit_price=Decimal('1000.00'),
            discount=Decimal('500.00'),
            product_name_snapshot='Test',
            sku_snapshot='TEST-001',
        )
        # line_total = (5 * 1000) - 500 = 5000 - 500 = 4500
        self.assertEqual(item.line_total, Decimal('4500.00'))

    def test_negative_quantity_fails(self):
        """Test that negative quantities fail validation."""
        item = SaleItem(
            sale=self.sale,
            product=self.product,
            quantity=-1,
            unit_price=Decimal('1000.00'),
            product_name_snapshot='Test',
            sku_snapshot='TEST-001',
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_zero_quantity_fails(self):
        """Test that zero quantity fails validation."""
        item = SaleItem(
            sale=self.sale,
            product=self.product,
            quantity=0,
            unit_price=Decimal('1000.00'),
            product_name_snapshot='Test',
            sku_snapshot='TEST-001',
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_create_from_product_factory(self):
        """Test the create_from_product factory method."""
        item = SaleItem.create_from_product(
            product=self.product,
            sale=self.sale,
            quantity=3,
            discount=Decimal('100.00'),
        )
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.unit_price, Decimal('1000.00'))
        self.assertEqual(item.product_name_snapshot, 'Test Product')
        self.assertEqual(item.sku_snapshot, 'TEST-001')
        self.assertEqual(item.discount, Decimal('100.00'))

    def test_create_from_product_without_product_fails(self):
        """Test that create_from_product fails without a product."""
        with self.assertRaises(ValidationError):
            SaleItem.create_from_product(
                product=None,
                sale=self.sale,
                quantity=1,
            )

    def test_create_from_product_with_invalid_quantity_fails(self):
        """Test that create_from_product fails with invalid quantity."""
        with self.assertRaises(ValidationError):
            SaleItem.create_from_product(
                product=self.product,
                sale=self.sale,
                quantity=0,
            )


class DecimalMoneyTests(TestCase):
    """Tests for decimal money handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.category = ProductCategory.objects.create(
            name='DecimalTest',
            slug='decimal-test',
        )
        self.cashier = User.objects.create_user(
            email='cashier-decimal@example.com',
            username='cashier-decimal',
            password='Pass123',
            role='CASHIER',
        )

    def test_sale_uses_decimal_for_money(self):
        """Test that Sale uses DecimalField for all money amounts."""
        sale = Sale.objects.create(
            sale_number='MH-DECIMAL-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            subtotal=Decimal('12345.67'),
            discount=Decimal('123.45'),
            total=Decimal('12222.22'),
            amount_received=Decimal('15000.00'),
        )
        sale.refresh_from_db()
        self.assertIsInstance(sale.subtotal, Decimal)
        self.assertIsInstance(sale.discount, Decimal)
        self.assertIsInstance(sale.total, Decimal)

    def test_sale_item_uses_decimal_for_money(self):
        """Test that SaleItem uses DecimalField for prices."""
        sale = Sale.objects.create(
            sale_number='MH-DECIMAL-002',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )
        product = Product.objects.create(
            name='Money Test Product',
            slug='money-test-product',
            sku='MONEY-001',
            category=self.category,
            selling_price=Decimal('999.99'),
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=1,
            unit_price=Decimal('999.99'),
            discount=Decimal('99.99'),
            product_name_snapshot='Test',
            sku_snapshot='TEST',
        )
        item.refresh_from_db()
        self.assertIsInstance(item.unit_price, Decimal)
        self.assertIsInstance(item.discount, Decimal)

    def test_precision_preserved_in_calculations(self):
        """Test that decimal precision is preserved in calculations."""
        sale = Sale.objects.create(
            sale_number='MH-PRECISION-001',
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
        )
        product = Product.objects.create(
            name='Precision Test Product',
            slug='precision-test-product',
            sku='PREC-001',
            category=self.category,
            selling_price=Decimal('333.33'),
        )
        item = SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=3,
            unit_price=Decimal('333.33'),  # Results in 999.99 total
            discount=Decimal('0.01'),
            product_name_snapshot='Test',
            sku_snapshot='TEST',
        )
        # line_total = (3 * 333.33) - 0.01 = 999.99 - 0.01 = 999.98
        self.assertEqual(item.line_total, Decimal('999.98'))


class PaymentMethodValidationTests(TestCase):
    """Tests for payment method validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.cashier = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            password='Pass123',
            role='CASHIER',
        )

    def test_all_payment_methods_valid(self):
        """Test that all payment methods are supported."""
        for idx, (method, _) in enumerate(Sale.PaymentMethod.choices):
            sale = Sale(
                sale_number=f'MH-PAY-{method}-{idx}',
                cashier=self.cashier,
                payment_method=method,
            )
            if method == 'CREDIT':
                # Credit requires customer
                self.assertRaises(ValidationError, sale.full_clean)
            else:
                sale.full_clean()  # Should not raise


class DjangoSystemChecksTests(TestCase):
    """Tests for Django system checks."""

    def test_django_system_checks_pass(self):
        """Test that Django system checks pass."""
        from django.core.management import call_command

        call_command('check')  # Should not raise


class SalesReadApiTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(name='Sales Read API', slug='sales-read-api')
        self.product = Product.objects.create(
            name='Read API Product',
            slug='read-api-product',
            sku='READ-001',
            category=self.category,
            selling_price=Decimal('100.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=10)
        self.other_product = Product.objects.create(
            name='Second Read Product',
            slug='second-read-product',
            sku='READ-002',
            category=self.category,
            selling_price=Decimal('250.00'),
        )
        InventoryItem.objects.create(product=self.other_product, quantity=8)
        self.owner = User.objects.create_user(email='read-owner@example.com', username='read-owner', password='Pass123', role='OWNER')
        self.manager = User.objects.create_user(email='read-manager@example.com', username='read-manager', password='Pass123', role='MANAGER')
        self.cashier = User.objects.create_user(email='read-cashier@example.com', username='read-cashier', password='Pass123', role='CASHIER')
        self.staff = User.objects.create_user(email='read-staff@example.com', username='read-staff', password='Pass123', role='STAFF')
        self.customer = User.objects.create_user(email='read-customer@example.com', username='read-customer', password='Pass123', role='CUSTOMER')
        self.sale = self.make_sale('READ-SALE-001', self.cashier, 'CASH', Sale.SaleStatus.COMPLETED, self.product, 2)
        self.other_sale = self.make_sale('READ-SALE-002', self.manager, 'CARD', Sale.SaleStatus.DRAFT, self.other_product, 1)
        now = timezone.now()
        Sale.objects.filter(pk=self.sale.pk).update(created_at=now - timedelta(days=3), updated_at=now - timedelta(days=3))
        Sale.objects.filter(pk=self.other_sale.pk).update(created_at=now - timedelta(days=1), updated_at=now - timedelta(days=1))

    def make_sale(self, sale_number, cashier, payment_method, status, product, quantity, customer=None):
        sale = Sale.objects.create(
            sale_number=sale_number,
            cashier=cashier,
            customer=customer,
            payment_method=payment_method,
            status=status,
            payment_status='COMPLETED' if status == Sale.SaleStatus.COMPLETED else 'PENDING',
            subtotal=product.selling_price * quantity,
            total=product.selling_price * quantity,
            amount_received=product.selling_price * quantity if status == Sale.SaleStatus.COMPLETED else None,
            change_amount=Decimal('0.00') if status == Sale.SaleStatus.COMPLETED else None,
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=product.selling_price,
            discount=Decimal('0.00'),
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
        )
        return sale

    def test_sales_list_requires_authentication_and_allows_customer_own_sales_only(self):
        self.assertEqual(self.client.get('/sales/').status_code, 401)

        customer_sale = self.make_sale('READ-CUSTOMER-SALE', self.cashier, 'CASH', Sale.SaleStatus.COMPLETED, self.product, 1, customer=self.customer)
        self.client.force_login(self.customer)
        response = self.client.get('/sales/')
        self.assertEqual(response.status_code, 200)
        sales = response.json()['data']['sales']
        self.assertEqual([sale['id'] for sale in sales], [customer_sale.id])

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/sales/').status_code, 403)

    def test_sales_list_returns_paginated_sales_and_supports_filters(self):
        self.client.force_login(self.owner)
        response = self.client.get('/sales/', {'page_size': 1, 'page': 1})
        data = response.json()['data']
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['pagination']['total_count'], 2)
        self.assertEqual(len(data['sales']), 1)

        self.assertEqual(self.client.get('/sales/', {'search': 'READ-SALE-001'}).json()['data']['sales'][0]['id'], self.sale.id)
        self.assertEqual(self.client.get('/sales/', {'status': 'COMPLETED'}).json()['data']['sales'][0]['id'], self.sale.id)
        self.assertEqual(self.client.get('/sales/', {'payment_method': 'CARD'}).json()['data']['sales'][0]['id'], self.other_sale.id)
        self.assertEqual(self.client.get('/sales/', {'payment_status': 'PENDING'}).json()['data']['sales'][0]['id'], self.other_sale.id)
        self.assertEqual(self.client.get('/sales/', {'cashier_id': self.cashier.id}).json()['data']['sales'][0]['id'], self.sale.id)

    def test_sales_list_supports_date_filters_and_rejects_invalid_ranges(self):
        self.client.force_login(self.owner)
        now = timezone.localdate()
        response = self.client.get('/sales/', {'date_from': (now - timedelta(days=2)).isoformat()})
        self.assertEqual(response.json()['data']['pagination']['total_count'], 1)
        response = self.client.get('/sales/', {'date_to': (now - timedelta(days=2)).isoformat()})
        self.assertEqual(response.json()['data']['pagination']['total_count'], 1)
        self.assertEqual(self.client.get('/sales/', {'date_from': 'bad-date'}).status_code, 400)
        self.assertEqual(self.client.get('/sales/', {'date_from': '2026-08-25', 'date_to': '2026-08-20'}).status_code, 400)

    def test_sales_detail_returns_snapshot_data_and_requires_authorization(self):
        self.client.force_login(self.owner)
        response = self.client.get(f'/sales/{self.sale.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['id'], self.sale.id)
        self.assertEqual(data['items'][0]['product_name'], self.product.name)
        self.assertEqual(data['items'][0]['sku'], self.product.sku)
        self.assertEqual(data['items'][0]['unit_price'], '100.00')
        self.product.name = 'Changed Current Product'
        self.product.selling_price = Decimal('999.00')
        self.product.save()
        response = self.client.get(f'/sales/{self.sale.id}/')
        self.assertEqual(response.json()['data']['items'][0]['product_name'], 'Read API Product')
        self.assertEqual(response.json()['data']['items'][0]['unit_price'], '100.00')

        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(f'/sales/{self.sale.id}/').status_code, 403)

    def test_sales_read_api_handles_empty_404_405_and_bounded_queries(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/sales/', {'search': 'missing'}).json()['data']['pagination']['total_count'], 0)
        self.assertEqual(self.client.get('/sales/999999/').status_code, 404)
        self.assertEqual(self.client.post(f'/sales/{self.sale.id}/').status_code, 405)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(f'/sales/{self.sale.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 4)


class SalesApiTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(name='Sales API', slug='sales-api')
        self.product = Product.objects.create(
            name='API Product',
            slug='api-product',
            sku='SALES-API-001',
            category=self.category,
            selling_price=Decimal('125.50'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=10)
        self.inactive_product = Product.objects.create(
            name='Inactive API Product',
            slug='inactive-api-product',
            sku='SALES-API-002',
            category=self.category,
            selling_price=Decimal('50.00'),
            is_active=False,
        )
        self.owner = User.objects.create_user(
            email='sales-owner@example.com', username='sales-owner', password='Pass123', role='OWNER'
        )
        self.manager = User.objects.create_user(
            email='sales-manager@example.com', username='sales-manager', password='Pass123', role='MANAGER'
        )
        self.cashier = User.objects.create_user(
            email='sales-cashier@example.com', username='sales-cashier', password='Pass123', role='CASHIER'
        )
        self.customer = User.objects.create_user(
            email='sales-customer@example.com', username='sales-customer', password='Pass123', role='CUSTOMER'
        )

    def create_url(self):
        return '/sales/'

    def complete_url(self, sale):
        return f'/sales/{sale.id}/complete/'

    def post_json(self, url, payload):
        return self.client.post(url, data=payload, content_type='application/json')

    def valid_payload(self, **overrides):
        payload = {
            'customer_id': None,
            'payment_method': 'CASH',
            'discount': '0.00',
            'notes': '',
            'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '0.00'}],
        }
        payload.update(overrides)
        return payload

    def test_creation_requires_authentication_and_rejects_customer(self):
        response = self.post_json(self.create_url(), self.valid_payload())
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.customer)
        response = self.post_json(self.create_url(), self.valid_payload())
        self.assertEqual(response.status_code, 403)

    def test_owner_manager_and_cashier_can_create_drafts(self):
        for user in (self.owner, self.manager, self.cashier):
            self.client.force_login(user)
            response = self.post_json(self.create_url(), self.valid_payload())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['data']['sale']['status'], Sale.SaleStatus.DRAFT)

    def test_creation_validates_items_products_payment_credit_and_discounts(self):
        self.client.force_login(self.owner)
        invalid_payloads = [
            self.valid_payload(items=[]),
            self.valid_payload(payment_method='INVALID'),
            self.valid_payload(items=[{'product_id': 99999, 'quantity': 1}]),
            self.valid_payload(items=[{'product_id': self.inactive_product.id, 'quantity': 1}]),
            self.valid_payload(items=[{'product_id': self.product.id, 'quantity': 0}]),
            self.valid_payload(items=[{'product_id': self.product.id, 'quantity': -1}]),
            self.valid_payload(payment_method='CREDIT'),
            self.valid_payload(discount='-1.00'),
            self.valid_payload(items=[{'product_id': self.product.id, 'quantity': 1, 'discount': '126.00'}]),
        ]
        for payload in invalid_payloads:
            self.assertEqual(self.post_json(self.create_url(), payload).status_code, 400)

    def test_creation_uses_server_price_and_calculates_totals(self):
        self.client.force_login(self.owner)
        response = self.post_json(
            self.create_url(),
            self.valid_payload(
                discount='10.00',
                items=[{'product_id': self.product.id, 'quantity': 2, 'discount': '1.00'}],
            ),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['sale']['subtotal'], '250.00')
        self.assertEqual(data['sale']['total'], '240.00')
        self.assertEqual(data['items'][0]['unit_price'], '125.50')
        self.assertEqual(data['items'][0]['line_total'], '250.00')
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)

    def test_completion_requires_authentication_authorization_and_valid_method(self):
        sale = self.create_sale()
        response = self.post_json(self.complete_url(sale), {})
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.customer)
        self.assertEqual(self.post_json(self.complete_url(sale), {}).status_code, 403)

        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(self.complete_url(sale)).status_code, 405)

    def test_completion_deducts_inventory_and_returns_sale_data(self):
        sale = self.create_sale()
        self.client.force_login(self.cashier)
        response = self.post_json(self.complete_url(sale), {'amount_received': '251.00'})

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['sale_number'], sale.sale_number)
        self.assertEqual(data['status'], Sale.SaleStatus.COMPLETED)
        self.assertEqual(data['payment_status'], Sale.PaymentStatus.COMPLETED)
        self.assertEqual(data['subtotal'], '251.00')
        self.assertEqual(data['amount_received'], '251.00')
        self.assertEqual(data['change_amount'], '0.00')
        self.assertIn('completed_at', data)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 8)
        movement = StockMovement.objects.get(reference=sale.sale_number)
        self.assertEqual(movement.quantity, -2)

    def test_completion_rolls_back_on_insufficient_stock_and_rejects_non_draft(self):
        sale = self.create_sale(quantity=20)
        self.client.force_login(self.owner)
        response = self.post_json(self.complete_url(sale), {})
        self.assertEqual(response.status_code, 400)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.assertEqual(StockMovement.objects.count(), 0)

        sale.status = Sale.SaleStatus.COMPLETED
        sale.save(update_fields=['status'])
        self.assertEqual(self.post_json(self.complete_url(sale), {}).status_code, 409)

    def test_completion_rejects_empty_draft_and_missing_sale(self):
        sale = Sale.objects.create(
            sale_number='MH-EMPTY-API',
            cashier=self.owner,
            payment_method=Sale.PaymentMethod.CASH,
        )
        self.client.force_login(self.owner)
        self.assertEqual(self.post_json(self.complete_url(sale), {}).status_code, 400)
        self.assertEqual(self.post_json('/sales/999999/complete/', {}).status_code, 404)

    def create_sale(self, quantity=2):
        sale = Sale.objects.create(
            sale_number=f'MH-API-{uuid4().hex[:8].upper()}',
            cashier=self.owner,
            payment_method=Sale.PaymentMethod.CASH,
            subtotal=Decimal('251.00'),
            total=Decimal('251.00'),
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=quantity,
            unit_price=Decimal('125.50'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        return sale


class SalesPaymentApiTests(TestCase):
    def setUp(self):
        category = ProductCategory.objects.create(name='Sales Payment API', slug='sales-payment-api')
        self.product = Product.objects.create(
            name='Payment API Product',
            slug='payment-api-product',
            sku='PAYMENT-001',
            category=category,
            selling_price=Decimal('7500.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=10)
        self.owner = User.objects.create_user(email='payment-owner@example.com', username='payment-owner', password='Pass123', role='OWNER')
        self.cashier = User.objects.create_user(email='payment-cashier@example.com', username='payment-cashier', password='Pass123', role='CASHIER')
        self.customer = User.objects.create_user(email='payment-customer@example.com', username='payment-customer', password='Pass123', role='CUSTOMER')
        self.credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

    def complete_url(self, sale):
        return f'/sales/{sale.id}/complete/'

    def post_json(self, url, payload):
        return self.client.post(url, data=payload, content_type='application/json')

    def create_sale(self, payment_method='CASH', quantity=1, customer=None):
        sale = Sale.objects.create(
            sale_number=f'MH-PAY-{uuid4().hex[:8].upper()}',
            cashier=self.cashier,
            customer=customer,
            payment_method=payment_method,
            subtotal=self.product.selling_price * quantity,
            total=self.product.selling_price * quantity,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=quantity,
            unit_price=self.product.selling_price,
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        return sale

    def test_cash_exact_and_overpayment_persist_amount_and_change(self):
        self.client.force_login(self.cashier)
        exact_sale = self.create_sale()
        exact_response = self.post_json(self.complete_url(exact_sale), {'amount_received': '7500.00'})
        self.assertEqual(exact_response.status_code, 200)
        exact_sale.refresh_from_db()
        self.assertEqual(exact_sale.amount_received, Decimal('7500.00'))
        self.assertEqual(exact_sale.change_amount, Decimal('0.00'))

        over_sale = self.create_sale()
        over_response = self.post_json(self.complete_url(over_sale), {'amount_received': '10000.00'})
        self.assertEqual(over_response.status_code, 200)
        over_sale.refresh_from_db()
        self.assertEqual(over_sale.amount_received, Decimal('10000.00'))
        self.assertEqual(over_sale.change_amount, Decimal('2500.00'))
        self.assertEqual(over_response.json()['data']['change_amount'], '2500.00')

    def test_cash_rejects_missing_invalid_negative_and_insufficient_payment(self):
        self.client.force_login(self.cashier)
        for amount in (None, 'abc', '-1.00', '7499.99'):
            sale = self.create_sale()
            payload = {} if amount is None else {'amount_received': amount}
            response = self.post_json(self.complete_url(sale), payload)
            self.assertEqual(response.status_code, 400)
            sale.refresh_from_db()
            self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
            self.assertIsNone(sale.amount_received)
            self.assertEqual(StockMovement.objects.filter(reference=sale.sale_number).count(), 0)

    def test_transfer_and_card_are_exact_and_reject_inconsistent_amounts(self):
        self.client.force_login(self.cashier)
        for payment_method in (Sale.PaymentMethod.TRANSFER, Sale.PaymentMethod.CARD):
            sale = self.create_sale(payment_method=payment_method)
            response = self.post_json(self.complete_url(sale), {})
            self.assertEqual(response.status_code, 200)
            sale.refresh_from_db()
            self.assertEqual(sale.amount_received, Decimal('7500.00'))
            self.assertEqual(sale.change_amount, Decimal('0.00'))

            inconsistent_sale = self.create_sale(payment_method=payment_method)
            response = self.post_json(self.complete_url(inconsistent_sale), {'amount_received': '8000.00'})
            self.assertEqual(response.status_code, 400)
            inconsistent_sale.refresh_from_db()
            self.assertEqual(inconsistent_sale.status, Sale.SaleStatus.DRAFT)

    def test_credit_persists_zero_payment_values(self):
        self.client.force_login(self.cashier)
        sale = self.create_sale(payment_method=Sale.PaymentMethod.CREDIT, customer=self.customer)
        response = self.post_json(self.complete_url(sale), {})
        self.assertEqual(response.status_code, 200)
        sale.refresh_from_db()
        self.assertEqual(sale.amount_received, Decimal('0.00'))
        self.assertEqual(sale.change_amount, Decimal('0.00'))
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, sale.total)
        self.assertEqual(self.credit_account.status, CreditAccount.Status.ACTIVE)
        tx = CreditTransaction.objects.get(sale=sale)
        self.assertEqual(tx.credit_account, self.credit_account)
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.CREDIT_PURCHASE)
        self.assertEqual(tx.amount, sale.total)
        self.assertEqual(tx.created_by, self.cashier)

    def test_payment_validation_and_inventory_failure_leave_sale_and_stock_unchanged(self):
        self.client.force_login(self.owner)
        sale = self.create_sale(quantity=20)
        response = self.post_json(self.complete_url(sale), {'amount_received': '150000.00'})
        self.assertEqual(response.status_code, 400)
        sale.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.assertIsNone(sale.amount_received)
        self.assertIsNone(sale.change_amount)
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.filter(reference=sale.sale_number).count(), 0)

        invalid_sale = self.create_sale()
        response = self.post_json(self.complete_url(invalid_sale), {'amount_received': '1.00'})
        self.assertEqual(response.status_code, 400)
        invalid_sale.refresh_from_db()
        self.assertIsNone(invalid_sale.amount_received)

    def test_completion_authorization_and_completed_conflict(self):
        sale = self.create_sale()
        self.assertEqual(self.post_json(self.complete_url(sale), {'amount_received': '7500.00'}).status_code, 401)

        self.client.force_login(self.customer)
        self.assertEqual(self.post_json(self.complete_url(sale), {'amount_received': '7500.00'}).status_code, 403)

        self.client.force_login(self.owner)
        self.assertEqual(self.post_json(self.complete_url(sale), {'amount_received': '7500.00'}).status_code, 200)
        self.assertEqual(self.post_json(self.complete_url(sale), {'amount_received': '7500.00'}).status_code, 409)


class SalesCustomerAccessTests(TestCase):
    def setUp(self):
        category = ProductCategory.objects.create(name='Sales Customer API', slug='sales-customer-api')
        product = Product.objects.create(
            name='Customer Sales Product',
            slug='customer-sales-product',
            sku='CUSTOMER-001',
            category=category,
            selling_price=Decimal('100.00'),
        )
        self.owner = User.objects.create_user(email='customer-access-owner@example.com', username='customer-access-owner', password='Pass123', role='OWNER')
        self.customer = User.objects.create_user(email='customer-access-one@example.com', username='customer-access-one', password='Pass123', role='CUSTOMER')
        self.other_customer = User.objects.create_user(email='customer-access-two@example.com', username='customer-access-two', password='Pass123', role='CUSTOMER')
        self.own_sale = self.create_sale('CUSTOMER-SALE-001', self.customer, product)
        self.other_sale = self.create_sale('CUSTOMER-SALE-002', self.other_customer, product)

    def create_sale(self, sale_number, customer, product):
        sale = Sale.objects.create(
            sale_number=sale_number,
            customer=customer,
            cashier=self.owner,
            payment_method=Sale.PaymentMethod.CASH,
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
        )
        return sale

    def test_unauthenticated_customer_isolation_and_own_sales(self):
        self.assertEqual(self.client.get('/sales/').status_code, 401)
        self.client.force_login(self.customer)
        response = self.client.get('/sales/')
        self.assertEqual(response.status_code, 200)
        sales = response.json()['data']['sales']
        self.assertEqual([sale['id'] for sale in sales], [self.own_sale.id])
        self.assertEqual(self.client.get('/sales/', {'customer_id': self.other_customer.id}).json()['data']['sales'][0]['id'], self.own_sale.id)
        bypass_response = self.client.get('/sales/', {'customer': self.other_customer.id, 'search': self.other_sale.sale_number})
        self.assertEqual(bypass_response.json()['data']['sales'], [])

    def test_customer_can_view_own_sale_but_not_another_customer_sale(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(f'/sales/{self.own_sale.id}/').status_code, 200)
        response = self.client.get(f'/sales/{self.other_sale.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.other_sale.sale_number, response.content.decode())

    def test_empty_customer_sales_is_paginated_and_management_roles_retain_access(self):
        empty_customer = User.objects.create_user(email='customer-access-empty@example.com', username='customer-access-empty', password='Pass123', role='CUSTOMER')
        self.client.force_login(empty_customer)
        data = self.client.get('/sales/').json()['data']
        self.assertEqual(data['sales'], [])
        self.assertEqual(data['pagination']['total_count'], 0)

        for role in ('OWNER', 'MANAGER', 'CASHIER'):
            user = self.owner if role == 'OWNER' else User.objects.create_user(email=f'{role.lower()}-access@example.com', username=f'{role.lower()}-access', password='Pass123', role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.get('/sales/').status_code, 200)


class SalesReportingApiTests(TestCase):
    def setUp(self):
        category = ProductCategory.objects.create(name='Sales Reporting API', slug='sales-reporting-api')
        product = Product.objects.create(name='Reporting Product', slug='reporting-product', sku='REPORT-001', category=category, selling_price=Decimal('100.00'))
        self.owner = User.objects.create_user(email='report-owner@example.com', username='report-owner', password='Pass123', role='OWNER')
        self.staff = User.objects.create_user(email='report-staff@example.com', username='report-staff', password='Pass123', role='STAFF')
        self.customer = User.objects.create_user(email='report-customer@example.com', username='report-customer', password='Pass123', role='CUSTOMER')
        self.completed = self.make_sale('REPORT-COMPLETED', Sale.SaleStatus.COMPLETED, Sale.PaymentMethod.CASH, Decimal('100.00'), product)
        self.completed_transfer = self.make_sale('REPORT-TRANSFER', Sale.SaleStatus.COMPLETED, Sale.PaymentMethod.TRANSFER, Decimal('200.00'), product)
        self.draft = self.make_sale('REPORT-DRAFT', Sale.SaleStatus.DRAFT, Sale.PaymentMethod.CARD, Decimal('500.00'), product)
        now = timezone.now()
        Sale.objects.filter(pk=self.completed.pk).update(created_at=now - timedelta(days=3))
        Sale.objects.filter(pk=self.completed_transfer.pk).update(created_at=now - timedelta(days=1))

    def make_sale(self, sale_number, status, payment_method, total, product):
        sale = Sale.objects.create(
            sale_number=sale_number,
            cashier=self.owner,
            payment_method=payment_method,
            status=status,
            payment_status=Sale.PaymentStatus.COMPLETED if status == Sale.SaleStatus.COMPLETED else Sale.PaymentStatus.PENDING,
            subtotal=total,
            discount=Decimal('10.00'),
            total=total,
        )
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=total, product_name_snapshot=product.name, sku_snapshot=product.sku)
        return sale

    def test_summary_aggregates_completed_sales_only(self):
        self.client.force_login(self.owner)
        response = self.client.get('/sales/reports/summary/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['transaction_count'], 2)
        self.assertEqual(data['total_sales'], '300.00')
        self.assertEqual(data['total_discount'], '20.00')
        self.assertEqual(data['cash_total'], '100.00')
        self.assertEqual(data['transfer_total'], '200.00')
        self.assertEqual(data['card_total'], '0.00')
        self.assertEqual(data['credit_total'], '0.00')

    def test_summary_roles_dates_errors_and_methods(self):
        self.assertEqual(self.client.get('/sales/reports/summary/').status_code, 401)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/sales/reports/summary/').status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/sales/reports/summary/').status_code, 200)
        today = timezone.localdate()
        self.assertEqual(self.client.get('/sales/reports/summary/', {'date_from': (today - timedelta(days=2)).isoformat()}).json()['data']['transaction_count'], 1)
        self.assertEqual(self.client.get('/sales/reports/summary/', {'date_from': 'bad-date'}).status_code, 400)
        self.assertEqual(self.client.get('/sales/reports/summary/', {'date_from': '2026-08-25', 'date_to': '2026-08-20'}).status_code, 400)
        self.assertEqual(self.client.post('/sales/reports/summary/').status_code, 405)

    def test_summary_uses_bounded_query_count(self):
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/sales/reports/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 3)


class SalesCreditEnforcementTests(TestCase):
    """
    Dedicated tests for the Credit workflow enforcement on POS Sales.
    Verifies that credit sales enforce customer credit account existence,
    approval status, credit limit availability, atomic balance deduction,
    credit ledger transaction creation, and transactional rollback on failures.
    """

    def setUp(self):
        self.category = ProductCategory.objects.create(
            name='Fashion Credit',
            slug='fashion-credit',
        )
        self.product = Product.objects.create(
            name='Designer Lace Fabric',
            slug='designer-lace-fabric',
            sku='CRD-FAB-001',
            category=self.category,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('7000.00'),
        )
        self.inventory = InventoryItem.objects.create(
            product=self.product,
            quantity=10,
        )
        self.owner = User.objects.create_user(
            email='credit-owner@example.com',
            username='credit-owner',
            password='Pass123',
            role='OWNER',
        )
        self.cashier = User.objects.create_user(
            email='credit-cashier@example.com',
            username='credit-cashier',
            password='Pass123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='credit-cust@example.com',
            username='credit-cust',
            password='Pass123',
            role='CUSTOMER',
        )
        self.credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        self.customer_no_credit = User.objects.create_user(
            email='no-credit@example.com',
            username='no-credit',
            password='Pass123',
            role='CUSTOMER',
        )
        self.customer_suspended = User.objects.create_user(
            email='suspended-credit@example.com',
            username='suspended-credit',
            password='Pass123',
            role='CUSTOMER',
        )
        self.suspended_account = CreditAccount.objects.create(
            customer=self.customer_suspended,
            credit_limit=Decimal('20000.00'),
            outstanding_balance=Decimal('5000.00'),
            status=CreditAccount.Status.SUSPENDED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

    def _create_credit_sale(self, customer, quantity=1, cashier=None):
        cashier = cashier or self.cashier
        sale = Sale.objects.create(
            sale_number=f'MH-CRD-{uuid4().hex[:8].upper()}',
            cashier=cashier,
            customer=customer,
            payment_method=Sale.PaymentMethod.CREDIT,
            subtotal=self.product.selling_price * quantity,
            total=self.product.selling_price * quantity,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=quantity,
            unit_price=self.product.selling_price,
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        return sale

    def test_credit_sale_completion_success(self):
        """Valid credit purchase completes, deducts inventory, increases balance, and creates transaction."""
        self.client.force_login(self.cashier)
        sale = self._create_credit_sale(self.customer, quantity=2)  # total 20,000.00
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.COMPLETED)
        self.assertEqual(sale.amount_received, Decimal('0.00'))
        self.assertEqual(sale.change_amount, Decimal('0.00'))

        # Inventory verified
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 8)
        movement = StockMovement.objects.get(reference=sale.sale_number)
        self.assertEqual(movement.movement_type, 'STOCK_OUT')
        self.assertEqual(movement.quantity, -2)

        # Credit verified
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('20000.00'))
        self.assertEqual(self.credit_account.get_available_credit(), Decimal('30000.00'))
        self.assertEqual(self.credit_account.status, CreditAccount.Status.ACTIVE)

        tx = CreditTransaction.objects.get(sale=sale)
        self.assertEqual(tx.credit_account, self.credit_account)
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.CREDIT_PURCHASE)
        self.assertEqual(tx.amount, Decimal('20000.00'))
        self.assertEqual(tx.previous_balance, Decimal('0.00'))
        self.assertEqual(tx.new_balance, Decimal('20000.00'))
        self.assertEqual(tx.created_by, self.cashier)

    def test_credit_sale_completion_exact_limit(self):
        """Credit purchase matching exactly the available credit succeeds."""
        self.client.force_login(self.cashier)
        # Account has 50k limit; make a 5-item sale = 50,000.00
        sale = self._create_credit_sale(self.customer, quantity=5)
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('50000.00'))
        self.assertEqual(self.credit_account.get_available_credit(), Decimal('0.00'))
        self.assertFalse(self.credit_account.can_use_credit(Decimal('0.01')))

    def test_credit_sale_rejected_without_credit_account(self):
        """Credit purchase fails if customer has no credit account, leaving inventory and sale intact."""
        self.client.force_login(self.cashier)
        sale = self._create_credit_sale(self.customer_no_credit, quantity=1)
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.filter(reference=sale.sale_number).count(), 0)
        self.assertEqual(CreditTransaction.objects.filter(sale=sale).count(), 0)

    def test_credit_sale_rejected_if_account_suspended(self):
        """Suspended credit account cannot complete credit purchase."""
        self.client.force_login(self.cashier)
        sale = self._create_credit_sale(self.customer_suspended, quantity=1)
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.suspended_account.refresh_from_db()
        self.assertEqual(self.suspended_account.outstanding_balance, Decimal('5000.00'))

    def test_credit_sale_rejected_if_exceeds_credit_limit(self):
        """Credit purchase exceeding available credit fails validation."""
        self.client.force_login(self.cashier)
        # Limit is 50,000; try 6 items = 60,000
        sale = self._create_credit_sale(self.customer, quantity=6)
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('0.00'))
        self.assertEqual(CreditTransaction.objects.filter(sale=sale).count(), 0)

    def test_credit_sale_rollback_on_inventory_failure(self):
        """If inventory adjustment fails (insufficient stock), credit balance is not deducted."""
        self.inventory.quantity = 1
        self.inventory.save()

        self.client.force_login(self.cashier)
        sale = self._create_credit_sale(self.customer, quantity=2)  # requires 2, stock is 1
        response = self.client.post(f'/sales/{sale.id}/complete/', {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('0.00'))
        self.assertEqual(CreditTransaction.objects.filter(sale=sale).count(), 0)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 1)

    def test_direct_complete_sale_model_method_enforces_credit(self):
        """Calling sale.complete_sale() directly in Python enforces credit rules and creates transaction."""
        sale = self._create_credit_sale(self.customer, quantity=1)
        sale.complete_sale()

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('10000.00'))
        tx = CreditTransaction.objects.get(sale=sale)
        self.assertEqual(tx.amount, Decimal('10000.00'))

    def test_direct_complete_sale_model_method_raises_on_exceeded_credit(self):
        """Direct call to sale.complete_sale() raises ValidationError if credit exceeded."""
        sale = self._create_credit_sale(self.customer, quantity=6)  # 60,000 > 50,000
        with self.assertRaises(ValidationError):
            sale.complete_sale()

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('0.00'))
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)


class ManagementOperationsDashboardTests(TestCase):
    """Comprehensive test suite for Management Operations Dashboards (Owner & Staff Live Views)."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner_user',
            email='owner@test.com',
            password='password123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='manager_user',
            email='manager@test.com',
            password='password123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='cashier_user',
            email='cashier@test.com',
            password='password123',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            username='staff_user',
            email='staff@test.com',
            password='password123',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='customer_user',
            email='customer@test.com',
            password='password123',
            role='CUSTOMER',
        )

        self.category = ProductCategory.objects.create(
            name='Dashboard Cat',
            slug='dashboard-cat',
        )
        # Low stock item: reorder_level=5, quantity=2
        self.product_low = Product.objects.create(
            name='Low Stock Item',
            slug='low-stock-item',
            sku='DASH-LOW-1',
            category=self.category,
            selling_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00'),
            reorder_level=5,
        )
        self.inv_low = InventoryItem.objects.create(
            product=self.product_low,
            quantity=2,
        )

        # Normal stock item: reorder_level=5, quantity=25
        self.product_normal = Product.objects.create(
            name='Normal Item',
            slug='normal-item',
            sku='DASH-NORM-1',
            category=self.category,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('6000.00'),
            reorder_level=5,
        )
        self.inv_normal = InventoryItem.objects.create(
            product=self.product_normal,
            quantity=25,
        )

        # Completed sale today: total=10,000, cost=6,000 -> profit=4,000
        self.today_sale = Sale.objects.create(
            sale_number='MH-SALE-TODAY-01',
            cashier=self.cashier,
            customer=self.customer,
            subtotal=Decimal('10000.00'),
            total=Decimal('10000.00'),
            payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        SaleItem.objects.create(
            sale=self.today_sale,
            product=self.product_normal,
            quantity=1,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product_normal.name,
            sku_snapshot=self.product_normal.sku,
        )

        # Active orders (CONFIRMED, PROCESSING) and COMPLETED order
        self.order_confirmed = Order.objects.create(
            order_number='MH-ORD-DASH-1',
            customer=self.customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('5000.00'),
        )
        self.order_processing = Order.objects.create(
            order_number='MH-ORD-DASH-2',
            customer=self.customer,
            status=Order.OrderStatus.PROCESSING,
            payment_method=Order.PaymentMethod.TRANSFER,
            total=Decimal('7000.00'),
        )
        self.order_completed = Order.objects.create(
            order_number='MH-ORD-DASH-3',
            customer=self.customer,
            status=Order.OrderStatus.COMPLETED,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('3000.00'),
        )

        # Pending Expense
        self.pending_expense = Expense.objects.create(
            expense_reference='EXP-DASH-01',
            category=Expense.Category.SUPPLIES,
            amount=Decimal('4500.00'),
            expense_date=timezone.now().date(),
            vendor='Stationery Hub',
            status=Expense.Status.PENDING,
            recorded_by=self.owner,
        )
        # Approved Expense
        self.approved_expense = Expense.objects.create(
            expense_reference='EXP-DASH-02',
            category=Expense.Category.UTILITIES,
            amount=Decimal('8000.00'),
            expense_date=timezone.now().date(),
            vendor='Power Corp',
            status=Expense.Status.APPROVED,
            recorded_by=self.owner,
        )

        # Outstanding Credit Account
        self.credit_acc, _ = CreditAccount.objects.get_or_create(
            customer=self.customer,
            defaults={'credit_limit': Decimal('50000.00')},
        )
        self.credit_acc.outstanding_balance = Decimal('12500.00')
        self.credit_acc.save()

        # Customer Request
        self.request_pending = Request.objects.create(
            request_number='REQ-DASH-01',
            customer=self.customer,
            title='Lace Material',
            description='Customer requesting lace material.',
            status=Request.Status.PENDING,
        )

        # Activity Log
        self.activity_log = ActivityLog.objects.create(
            actor=self.owner,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='Item Created',
            description='Created dashboard inventory item',
        )

    def test_unauthenticated_user_redirects_to_login_on_html(self):
        """Unauthenticated HTML request to /dashboard/ redirects to login."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertIn('next=/dashboard/', response.url)

    def test_unauthenticated_user_returns_401_on_json(self):
        """Unauthenticated JSON request to /dashboard/ returns 401 Unauthorized."""
        response = self.client.get('/dashboard/?format=json')
        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('Authentication required', payload['message'])

        response_header = self.client.get('/dashboard/', HTTP_ACCEPT='application/json')
        self.assertEqual(response_header.status_code, 401)

    def test_customer_redirects_to_customer_dashboard_on_html(self):
        """Customer accessing /dashboard/ via HTML is redirected to customer dashboard."""
        self.client.force_login(self.customer)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/customer/dashboard/')

    def test_customer_returns_403_on_json(self):
        """Customer requesting JSON from /dashboard/ receives 403 Forbidden."""
        self.client.force_login(self.customer)
        response = self.client.get('/dashboard/?format=json')
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('Customers cannot access the management dashboard', payload['message'])

    def test_owner_receives_owner_dashboard_html(self):
        """Owner receives owner.html with serialized context."""
        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/owner.html')
        self.assertIn('dashboard_json', response.context)
        self.assertContains(response, 'id="owner-dashboard-data"')

    def test_manager_receives_owner_dashboard_html(self):
        """Manager receives owner.html with serialized context."""
        self.client.force_login(self.manager)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/owner.html')
        self.assertIn('dashboard_json', response.context)

    def test_cashier_receives_staff_dashboard_html(self):
        """Cashier receives staff.html with operational context."""
        self.client.force_login(self.cashier)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/staff.html')
        self.assertIn('dashboard_json', response.context)
        self.assertContains(response, 'id="staff-dashboard-data"')

    def test_staff_receives_staff_dashboard_html(self):
        """Staff receives staff.html with operational context."""
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/staff.html')
        self.assertIn('dashboard_json', response.context)

    def test_owner_json_payload_and_metrics_accuracy(self):
        """Owner JSON payload accurately aggregates live business and financial metrics."""
        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/?format=json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        data = payload['data']

        self.assertEqual(data['role'], 'OWNER')
        metrics = data['metrics']
        self.assertEqual(metrics['todaySales'], 10000.0)
        self.assertEqual(metrics['todayProfit'], 4000.0)
        self.assertEqual(metrics['pending_expenses_count'], 1)
        self.assertEqual(metrics['active_orders_count'], 2)
        self.assertEqual(metrics['low_stock_count'], 1)
        self.assertEqual(metrics['outstandingCredit'], 12500.0)

        # Audit logs
        self.assertTrue(len(data['recent_activity']) >= 1)
        self.assertEqual(data['recent_activity'][0]['action_label'], 'Item Created')

    def test_cashier_staff_json_payload_and_financial_isolation(self):
        """Cashier JSON payload returns operational queues and conceals owner financials."""
        self.client.force_login(self.cashier)
        response = self.client.get('/dashboard/?format=json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        data = payload['data']

        self.assertEqual(data['role'], 'STAFF')
        metrics = data['metrics']
        self.assertEqual(metrics['ordersToPrepare'], 2)
        self.assertEqual(metrics['stockChecks'], 1)
        self.assertEqual(metrics['requestsToReview'], 1)
        self.assertEqual(metrics['todayTransactions'], 1)

        # Financial isolation verification: staff payload must NOT leak profit, unapproved expenses, or credit
        self.assertNotIn('todayProfit', metrics)
        self.assertNotIn('outstandingCredit', metrics)
        self.assertNotIn('monthlySales', metrics)
        self.assertNotIn('pending_expenses_count', metrics)
        self.assertNotIn('recent_activity', data)

    def test_post_method_not_allowed(self):
        """POST method is rejected with 405 Method Not Allowed."""
        self.client.force_login(self.owner)
        response = self.client.post('/dashboard/')
        self.assertEqual(response.status_code, 405)

    def test_url_reversals(self):
        """Management dashboard URL names resolve correctly."""
        from django.urls import reverse
        self.assertEqual(reverse('management_dashboard'), '/dashboard/')
        self.assertEqual(reverse('sales:dashboard'), '/sales/dashboard/')


class POSTemplateRenderingTests(TestCase):
    """Verify POS and checkout templates render without VariableDoesNotExist errors."""

    def setUp(self):
        self.cashier = User.objects.create_user(
            username='cashier_pos_template_test',
            password='password123',
            role='CASHIER',
        )

    def test_pos_view_renders_cleanly_without_variable_does_not_exist(self):
        """Navigating to /sales/pos/ renders 200 OK without VariableDoesNotExist crashes."""
        self.client.force_login(self.cashier)
        response = self.client.get('/sales/pos/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('posFallbackRefValue', content)
        self.assertIn('posFallbackAccountNumber', content)

    def test_sales_checkout_template_renders_without_variable_does_not_exist(self):
        """sales/checkout.html renders with empty context without VariableDoesNotExist crashes."""
        from django.template.loader import render_to_string
        rendered = render_to_string('sales/checkout.html', {})
        self.assertIn('fallbackRefValue', rendered)
        self.assertIn('fallbackAccountNumber', rendered)


class SalesCreditPaymentTests(TestCase):
    """Tests for Pay with Store Credit in Sales/POS."""

    def setUp(self):
        self.category = ProductCategory.objects.create(name='POS Category', slug='pos-cat')
        self.product = Product.objects.create(
            name='POS Retail Shirt',
            slug='pos-retail-shirt',
            sku='POS-SHIRT-01',
            category=self.category,
            selling_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=15)

        self.owner = User.objects.create_user(
            email='owner_pos_credit@example.com',
            username='owner_pos_credit',
            password='Password123',
            role='OWNER',
        )
        self.cashier = User.objects.create_user(
            email='cashier_pos_credit@example.com',
            username='cashier_pos_credit',
            password='Password123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='customer_pos_credit@example.com',
            username='customer_pos_credit',
            password='Password123',
            role='CUSTOMER',
            first_name='Tunde',
            last_name='Bakare',
            phone_number='08012345678',
        )
        self.credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('20000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

    def test_customer_can_pay_with_sufficient_credit(self):
        """Sale succeeds, inventory decreases, debt increases."""
        self.client.force_login(self.cashier)
        create_resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'customer_id': self.customer.id,
                'payment_method': 'CREDIT',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 3, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 200)
        sale_id = create_resp.json()['data']['sale']['id']

        complete_resp = self.client.post(
            f'/sales/{sale_id}/complete/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(complete_resp.status_code, 200)

        # Inventory decreases
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 12)

        # Debt increases
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('15000.00'))
        self.assertEqual(self.credit_account.current_balance, Decimal('15000.00'))
        self.assertEqual(self.credit_account.available_credit, Decimal('5000.00'))

    def test_customer_cannot_exceed_credit_limit(self):
        """Rejects with 400 error and helpful message."""
        self.client.force_login(self.cashier)
        # 5 units * 5000 = 25000 > credit limit 20000
        create_resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'customer_id': self.customer.id,
                'payment_method': 'CREDIT',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 5, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 400)
        data = create_resp.json()
        self.assertFalse(data['success'])
        err_msg = str(data.get('errors') or data.get('message'))
        self.assertTrue('credit' in err_msg.lower() or 'limit' in err_msg.lower())

    def test_credit_transaction_audit_logged(self):
        """Confirms CreditTransaction record exists with correct amount and user."""
        self.client.force_login(self.cashier)
        create_resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'customer_id': self.customer.id,
                'payment_method': 'CREDIT',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        sale_id = create_resp.json()['data']['sale']['id']
        complete_resp = self.client.post(
            f'/sales/{sale_id}/complete/',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(complete_resp.status_code, 200)

        tx = CreditTransaction.objects.filter(credit_account=self.credit_account).latest('created_at')
        self.assertEqual(tx.amount, Decimal('10000.00'))
        self.assertEqual(tx.created_by, self.cashier)
        self.assertEqual(tx.type, 'DEBIT')
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.CREDIT_PURCHASE)

    def test_customer_search_endpoint(self):
        """Customer search endpoint returns credit balance details."""
        self.client.force_login(self.cashier)
        resp = self.client.get('/sales/customers/search/?q=Tunde')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']['customers']
        self.assertTrue(any(c['id'] == self.customer.id for c in data))
        found = next(c for c in data if c['id'] == self.customer.id)
        self.assertEqual(found['credit_limit'], '20000.00')
        self.assertEqual(found['available_credit'], '20000.00')


class SaleCostPriceFloorTests(TestCase):
    def setUp(self):
        self.category = ProductCategory.objects.create(name='Provisions', slug='provisions')
        self.product = Product.objects.create(
            name='Peak Milk Powder 400g',
            sku='PM-400G',
            category=self.category,
            cost_price=Decimal('2000.00'),
            selling_price=Decimal('2600.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=50)
        self.cashier = User.objects.create_user(
            email='cashier-floor@example.com',
            username='cashierfloor',
            password='Password123',
            role='CASHIER',
        )

    def test_line_discount_below_cost_rejected(self):
        self.client.force_login(self.cashier)
        resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'payment_method': 'CASH',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '1500.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('Line discount causes effective selling price to fall below cost price', str(data['errors']))

    def test_sale_total_discount_below_cost_rejected(self):
        self.client.force_login(self.cashier)
        resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'payment_method': 'CASH',
                'discount': '1500.00',
                'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('Sale discount causes effective sale total to fall below total product cost price', str(data['errors']))

    def test_sale_at_cost_price_break_even_permitted(self):
        self.client.force_login(self.cashier)
        resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'payment_method': 'CASH',
                'discount': '1200.00',
                'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['sale']['total'], '4000.00')
