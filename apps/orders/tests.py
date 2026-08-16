from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.products.models import Product, ProductCategory
from .models import Order, OrderItem


class OrderModelTests(TestCase):
    """Test Order model creation, validation, and basic behavior."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests in this class."""
        cls.category = ProductCategory.objects.create(
            name='Test Category',
            slug='test-category'
        )
        cls.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
            first_name='Test',
            last_name='Customer'
        )
        cls.staff = User.objects.create_user(
            email='staff@example.com',
            username='staff',
            password='testpass123',
            role='CASHIER',
            first_name='Test',
            last_name='Staff'
        )

    def test_order_creation(self):
        """Test basic order creation."""
        order = Order.objects.create(
            order_number='MH-ORD-10001',
            customer=self.customer,
            created_by=self.staff,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.CASH,
        )
        self.assertEqual(order.order_number, 'MH-ORD-10001')
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.status, Order.OrderStatus.PENDING)
        self.assertEqual(order.subtotal, Decimal('0.00'))

    def test_order_number_uniqueness(self):
        """Test that order numbers must be unique."""
        Order.objects.create(
            order_number='MH-ORD-10001',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        with self.assertRaises(ValidationError):
            order = Order(
                order_number='MH-ORD-10001',
                customer=self.customer,
                payment_method=Order.PaymentMethod.CASH,
            )
            order.full_clean()

    def test_order_without_customer(self):
        """Test that orders can be created without a customer."""
        order = Order.objects.create(
            order_number='MH-ORD-10002',
            payment_method=Order.PaymentMethod.CASH,
        )
        self.assertIsNone(order.customer)

    def test_all_payment_methods_valid(self):
        """Test all payment method choices are valid."""
        payment_methods = [
            Order.PaymentMethod.CASH,
            Order.PaymentMethod.TRANSFER,
            Order.PaymentMethod.CARD,
            Order.PaymentMethod.CREDIT,
        ]
        for i, method in enumerate(payment_methods):
            order = Order.objects.create(
                order_number=f'MH-ORD-100{i+10}',
                customer=self.customer,
                payment_method=method,
            )
            self.assertEqual(order.payment_method, method)

    def test_all_order_statuses_valid(self):
        """Test all order status choices are valid."""
        statuses = [
            Order.OrderStatus.PENDING,
            Order.OrderStatus.CONFIRMED,
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.READY,
            Order.OrderStatus.COMPLETED,
            Order.OrderStatus.CANCELLED,
        ]
        for i, status in enumerate(statuses):
            order = Order.objects.create(
                order_number=f'MH-ORD-200{i+10}',
                customer=self.customer,
                payment_method=Order.PaymentMethod.CASH,
                status=status,
            )
            self.assertEqual(order.status, status)

    def test_order_default_status_is_pending(self):
        """Test that default order status is PENDING."""
        order = Order.objects.create(
            order_number='MH-ORD-10003',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        self.assertEqual(order.status, Order.OrderStatus.PENDING)

    def test_order_default_payment_status_is_pending(self):
        """Test that default payment status is PENDING."""
        order = Order.objects.create(
            order_number='MH-ORD-10004',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_negative_subtotal_validation(self):
        """Test that negative subtotal raises ValidationError."""
        order = Order(
            order_number='MH-ORD-10005',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            subtotal=Decimal('-100.00'),
        )
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_negative_discount_validation(self):
        """Test that negative discount raises ValidationError."""
        order = Order(
            order_number='MH-ORD-10006',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            discount=Decimal('-50.00'),
        )
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_negative_total_validation(self):
        """Test that negative total raises ValidationError."""
        order = Order(
            order_number='MH-ORD-10007',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('-200.00'),
        )
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_order_str_representation(self):
        """Test order string representation."""
        order = Order.objects.create(
            order_number='MH-ORD-10008',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        expected_str = f"Order MH-ORD-10008 - {order.get_status_display()}"
        self.assertEqual(str(order), expected_str)

    def test_order_with_delivery_address(self):
        """Test order with delivery address."""
        order = Order.objects.create(
            order_number='MH-ORD-10009',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            delivery_address='123 Main Street, Lagos',
        )
        self.assertEqual(order.delivery_address, '123 Main Street, Lagos')

    def test_order_with_customer_phone(self):
        """Test order with customer phone number."""
        order = Order.objects.create(
            order_number='MH-ORD-10010',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            customer_phone='+234812345678',
        )
        self.assertEqual(order.customer_phone, '+234812345678')


class OrderItemModelTests(TestCase):
    """Test OrderItem model and price snapshots."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests in this class."""
        cls.category = ProductCategory.objects.create(
            name='Test Category',
            slug='test-category'
        )
        cls.product = Product.objects.create(
            name='Test Product',
            sku='TST-001',
            category=cls.category,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('6000.00'),
        )
        cls.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.order = Order.objects.create(
            order_number='MH-ORD-10020',
            customer=cls.customer,
            payment_method=Order.PaymentMethod.CASH,
        )

    def test_order_item_creation(self):
        """Test basic OrderItem creation."""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=5,
            unit_price=self.product.selling_price,
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        self.assertEqual(item.quantity, 5)
        self.assertEqual(item.unit_price, Decimal('10000.00'))
        self.assertEqual(item.product_name_snapshot, 'Test Product')

    def test_order_item_line_total_calculation(self):
        """Test OrderItem line_total property calculation."""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=3,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        expected_line_total = Decimal('30000.00')
        self.assertEqual(item.line_total, expected_line_total)

    def test_order_item_price_snapshot_preserved_on_product_change(self):
        """Test that price snapshot is preserved when product price changes."""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        # Change product selling price
        self.product.selling_price = Decimal('15000.00')
        self.product.save()

        # Reload and verify snapshot is unchanged
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal('10000.00'))
        self.assertEqual(item.line_total, Decimal('20000.00'))

    def test_order_item_quantity_validation_positive(self):
        """Test that OrderItem quantity must be positive."""
        item = OrderItem(
            order=self.order,
            product=self.product,
            quantity=0,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_order_item_unit_price_non_negative(self):
        """Test that OrderItem unit_price cannot be negative."""
        item = OrderItem(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('-1000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_order_item_create_from_product_factory(self):
        """Test OrderItem.create_from_product factory method."""
        item = OrderItem.create_from_product(
            product=self.product,
            order=self.order,
            quantity=4,
        )
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, 4)
        self.assertEqual(item.unit_price, Decimal('10000.00'))
        self.assertEqual(item.product_name_snapshot, 'Test Product')
        self.assertEqual(item.sku_snapshot, 'TST-001')

    def test_order_item_create_from_product_invalid_quantity(self):
        """Test OrderItem factory with invalid quantity."""
        with self.assertRaises(ValidationError):
            OrderItem.create_from_product(
                product=self.product,
                order=self.order,
                quantity=0,
            )

    def test_order_item_create_from_product_no_product(self):
        """Test OrderItem factory with no product."""
        with self.assertRaises(ValidationError):
            OrderItem.create_from_product(
                product=None,
                order=self.order,
                quantity=1,
            )

    def test_order_item_str_representation(self):
        """Test OrderItem string representation."""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('10000.00'),
            product_name_snapshot='Test Product',
            sku_snapshot='TST-001',
        )
        expected_str = 'MH-ORD-10020 - Test Product x2'
        self.assertEqual(str(item), expected_str)


class OrderCalculationTests(TestCase):
    """Test Order total calculation logic."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests in this class."""
        cls.category = ProductCategory.objects.create(
            name='Test Category',
            slug='test-category'
        )
        cls.product1 = Product.objects.create(
            name='Product 1',
            sku='PRD-001',
            category=cls.category,
            selling_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00'),
        )
        cls.product2 = Product.objects.create(
            name='Product 2',
            sku='PRD-002',
            category=cls.category,
            selling_price=Decimal('8000.00'),
            cost_price=Decimal('5000.00'),
        )
        cls.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )

    def test_calculate_totals_single_item(self):
        """Test calculate_totals with single item."""
        order = Order.objects.create(
            order_number='MH-ORD-10030',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=2,
            unit_price=Decimal('5000.00'),
            product_name_snapshot=self.product1.name,
            sku_snapshot=self.product1.sku,
        )
        order.calculate_totals()
        self.assertEqual(order.subtotal, Decimal('10000.00'))
        self.assertEqual(order.total, Decimal('10000.00'))

    def test_calculate_totals_multiple_items(self):
        """Test calculate_totals with multiple items."""
        order = Order.objects.create(
            order_number='MH-ORD-10031',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=2,
            unit_price=Decimal('5000.00'),
            product_name_snapshot=self.product1.name,
            sku_snapshot=self.product1.sku,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product2,
            quantity=1,
            unit_price=Decimal('8000.00'),
            product_name_snapshot=self.product2.name,
            sku_snapshot=self.product2.sku,
        )
        order.calculate_totals()
        self.assertEqual(order.subtotal, Decimal('18000.00'))
        self.assertEqual(order.total, Decimal('18000.00'))

    def test_calculate_totals_with_discount(self):
        """Test calculate_totals with discount applied."""
        order = Order.objects.create(
            order_number='MH-ORD-10032',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            discount=Decimal('2000.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=3,
            unit_price=Decimal('5000.00'),
            product_name_snapshot=self.product1.name,
            sku_snapshot=self.product1.sku,
        )
        order.calculate_totals()
        self.assertEqual(order.subtotal, Decimal('15000.00'))
        self.assertEqual(order.total, Decimal('13000.00'))

    def test_calculate_totals_discount_exceeds_subtotal(self):
        """Test calculate_totals when discount exceeds subtotal (total clamped to 0)."""
        order = Order.objects.create(
            order_number='MH-ORD-10033',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            discount=Decimal('20000.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=1,
            unit_price=Decimal('5000.00'),
            product_name_snapshot=self.product1.name,
            sku_snapshot=self.product1.sku,
        )
        order.calculate_totals()
        self.assertEqual(order.subtotal, Decimal('5000.00'))
        self.assertEqual(order.total, Decimal('0.00'))

    def test_calculate_totals_empty_order(self):
        """Test calculate_totals with no items."""
        order = Order.objects.create(
            order_number='MH-ORD-10034',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        order.calculate_totals()
        self.assertEqual(order.subtotal, Decimal('0.00'))
        self.assertEqual(order.total, Decimal('0.00'))


class OrderNoInventoryDeductionTests(TestCase):
    """Test that Orders do NOT deduct inventory (unlike Sales)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests in this class."""
        from apps.inventory.models import InventoryItem

        cls.category = ProductCategory.objects.create(
            name='Test Category',
            slug='test-category'
        )
        cls.product = Product.objects.create(
            name='Test Product',
            sku='TST-001',
            category=cls.category,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('6000.00'),
        )
        InventoryItem.objects.create(product=cls.product, quantity=100)

        cls.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )

    def test_order_creation_does_not_deduct_inventory(self):
        """Test that creating an order does NOT affect inventory."""
        from apps.inventory.models import InventoryItem

        initial_stock = InventoryItem.objects.get(product=self.product).quantity

        order = Order.objects.create(
            order_number='MH-ORD-10040',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=10,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )

        final_stock = InventoryItem.objects.get(product=self.product).quantity
        self.assertEqual(initial_stock, final_stock)
        self.assertEqual(final_stock, 100)

    def test_order_status_change_does_not_deduct_inventory(self):
        """Test that changing order status does NOT affect inventory."""
        from apps.inventory.models import InventoryItem

        initial_stock = InventoryItem.objects.get(product=self.product).quantity

        order = Order.objects.create(
            order_number='MH-ORD-10041',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            status=Order.OrderStatus.PENDING,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=5,
            unit_price=Decimal('10000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )

        # Change status through various stages
        for status in [Order.OrderStatus.CONFIRMED, Order.OrderStatus.PROCESSING, Order.OrderStatus.COMPLETED]:
            order.status = status
            order.save()

        final_stock = InventoryItem.objects.get(product=self.product).quantity
        self.assertEqual(initial_stock, final_stock)
        self.assertEqual(final_stock, 100)


class DecimalMoneyTests(TestCase):
    """Test Decimal precision for monetary values in Orders."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests in this class."""
        cls.category = ProductCategory.objects.create(
            name='Test Category',
            slug='test-category'
        )
        cls.product = Product.objects.create(
            name='Test Product',
            sku='TST-001',
            category=cls.category,
            selling_price=Decimal('10000.99'),
            cost_price=Decimal('6000.50'),
        )
        cls.customer = User.objects.create_user(
            email='customer@example.com',
            username='customer',
            password='testpass123',
            role='CUSTOMER',
        )

    def test_order_decimal_precision_preserved(self):
        """Test that Decimal precision is preserved for order totals."""
        order = Order.objects.create(
            order_number='MH-ORD-10050',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            discount=Decimal('1000.50'),
        )
        # Create items with decimal prices
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('10000.99'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        order.calculate_totals()
        order.save()
        # After calculate_totals: subtotal = 10000.99, total = 10000.99 - 1000.50 = 9000.49
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal('10000.99'))
        self.assertEqual(order.discount, Decimal('1000.50'))
        expected_total = Decimal('9000.49')
        self.assertEqual(order.total, expected_total)

    def test_order_item_decimal_precision_preserved(self):
        """Test that Decimal precision is preserved for OrderItems."""
        item = OrderItem.objects.create(
            order=Order.objects.create(
                order_number='MH-ORD-10051',
                customer=self.customer,
                payment_method=Order.PaymentMethod.CASH,
            ),
            product=self.product,
            quantity=3,
            unit_price=Decimal('10000.99'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )
        # 3 × 10000.99 = 30002.97
        expected_line_total = Decimal('30002.97')
        self.assertEqual(item.line_total, expected_line_total)


class DjangoSystemChecksTests(TestCase):
    """Test Django system checks pass for Orders app."""

    def test_orders_app_checks_pass(self):
        """Test that django check passes."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('check', stdout=out)
        output = out.getvalue()
        # If no issues, output will mention "System check identified no issues"
        # or be empty in recent Django versions
        self.assertNotIn('error', output.lower())

