from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.inventory.models import InventoryItem, StockMovement
from apps.products.models import Product, ProductCategory
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
