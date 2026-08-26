import json
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.inventory.models import InventoryItem, StockMovement
from apps.notifications.models import Notification
from apps.products.models import Product, ProductCategory
from apps.sales.models import Sale, SaleItem
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


class OrdersApiTests(TestCase):
    """Focused tests for Order creation and read-only retrieval APIs."""

    @classmethod
    def setUpTestData(cls):
        cls.category = ProductCategory.objects.create(name='API Category', slug='api-category')
        cls.product = Product.objects.create(
            name='API Product',
            sku='API-001',
            category=cls.category,
            selling_price=Decimal('1250.50'),
            cost_price=Decimal('800.00'),
        )
        cls.second_product = Product.objects.create(
            name='Second API Product',
            sku='API-002',
            category=cls.category,
            selling_price=Decimal('300.00'),
            cost_price=Decimal('200.00'),
        )
        cls.inactive_product = Product.objects.create(
            name='Inactive API Product',
            sku='API-003',
            category=cls.category,
            selling_price=Decimal('100.00'),
            cost_price=Decimal('50.00'),
            is_active=False,
        )
        cls.customer = User.objects.create_user(
            email='api-customer@example.com',
            username='api-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.other_customer = User.objects.create_user(
            email='other-customer@example.com',
            username='other-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.manager = User.objects.create_user(
            email='api-manager@example.com',
            username='api-manager',
            password='testpass123',
            role='MANAGER',
        )

    def setUp(self):
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    def _post_order(self, payload):
        return self.client.post(
            '/orders/',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_unauthenticated_create_returns_401(self):
        response = self._post_order({'items': [{'product_id': self.product.id, 'quantity': 1}]})
        self.assertEqual(response.status_code, 401)

    def test_customer_can_create_with_server_side_totals_and_snapshots(self):
        self._login(self.customer)
        response = self._post_order({
            'items': [
                {'product_id': self.product.id, 'quantity': 2},
                {'product_id': self.second_product.id, 'quantity': 1},
            ],
            'customer_id': self.other_customer.id,
            'discount': '999999.99',
            'notes': 'Leave at the counter',
        })

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.status, Order.OrderStatus.PENDING)
        self.assertEqual(order.subtotal, Decimal('2801.00'))
        self.assertEqual(order.discount, Decimal('0.00'))
        self.assertEqual(order.total, Decimal('2801.00'))
        item = order.items.get(product=self.product)
        self.assertEqual(item.unit_price, Decimal('1250.50'))
        self.assertEqual(item.product_name_snapshot, 'API Product')
        self.assertEqual(item.sku_snapshot, 'API-001')

        self.product.selling_price = Decimal('9999.99')
        self.product.save()
        detail = self.client.get(f'/orders/{order.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['data']['order']['items'][0]['unit_price'], '1250.50')

    def test_management_can_list_but_cannot_create(self):
        self._login(self.manager)
        self.assertEqual(self.client.get('/orders/').status_code, 200)
        response = self._post_order({'items': [{'product_id': self.product.id, 'quantity': 1}]})
        self.assertEqual(response.status_code, 403)

    def test_invalid_items_are_atomic_and_do_not_create_order(self):
        self._login(self.customer)
        response = self._post_order({
            'items': [
                {'product_id': self.product.id, 'quantity': 1},
                {'product_id': self.inactive_product.id, 'quantity': 1},
            ],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_item_validation_rejects_empty_zero_negative_non_integer_and_duplicates(self):
        self._login(self.customer)
        payloads = [
            {'items': []},
            {'items': [{'product_id': self.product.id, 'quantity': 0}]},
            {'items': [{'product_id': self.product.id, 'quantity': -1}]},
            {'items': [{'product_id': self.product.id, 'quantity': 1.5}]},
            {'items': [
                {'product_id': self.product.id, 'quantity': 1},
                {'product_id': self.product.id, 'quantity': 2},
            ]},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self._post_order(payload).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_customer_list_and_detail_are_limited_to_own_orders(self):
        own_order = Order.objects.create(
            order_number='API-OWN',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        other_order = Order.objects.create(
            order_number='API-OTHER',
            customer=self.other_customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        self._login(self.customer)

        response = self.client.get('/orders/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()['data']['orders']], [own_order.id])
        self.assertEqual(self.client.get(f'/orders/{own_order.id}/').status_code, 200)
        self.assertEqual(self.client.get(f'/orders/{other_order.id}/').status_code, 403)

    def test_list_filters_dates_search_ordering_and_pagination(self):
        first = Order.objects.create(
            order_number='API-OLD', customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            status=Order.OrderStatus.COMPLETED, total=Decimal('10.00'),
        )
        second = Order.objects.create(
            order_number='API-NEW', customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            status=Order.OrderStatus.PENDING, total=Decimal('20.00'),
        )
        Order.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=2))
        Order.objects.filter(pk=second.pk).update(created_at=timezone.now())
        self._login(self.customer)

        response = self.client.get('/orders/?status=PENDING&search=NEW&page=1&page_size=1&ordering=total')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['pagination']['total_count'], 1)
        self.assertEqual(response.json()['data']['orders'][0]['order_number'], 'API-NEW')
        self.assertEqual(self.client.get('/orders/?date_from=2026-99-01').status_code, 400)
        self.assertEqual(self.client.get('/orders/?date_from=2026-08-20&date_to=2026-08-19').status_code, 400)

    def test_read_only_methods_return_405(self):
        self._login(self.customer)
        self.assertEqual(self.client.put('/orders/').status_code, 405)
        self.assertEqual(self.client.patch('/orders/').status_code, 405)
        self.assertEqual(self.client.delete('/orders/').status_code, 405)
        order = Order.objects.create(
            order_number='API-METHOD', customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(f'/orders/{order.id}/').status_code, 405)


class OrdersLifecycleApiTests(TestCase):
    """Focused tests for supported management lifecycle transitions."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            email='lifecycle-customer@example.com',
            username='lifecycle-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.other_customer = User.objects.create_user(
            email='lifecycle-other@example.com',
            username='lifecycle-other',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.manager = User.objects.create_user(
            email='lifecycle-manager@example.com',
            username='lifecycle-manager',
            password='testpass123',
            role='MANAGER',
        )

    def setUp(self):
        self.client = Client()
        self.order = Order.objects.create(
            order_number='LIFECYCLE-001',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
        )

    def _post_status(self, status):
        return self.client.post(
            f'/orders/{self.order.id}/status/',
            data=json.dumps({'status': status}),
            content_type='application/json',
        )

    def test_management_can_follow_valid_lifecycle(self):
        self.client.force_login(self.manager)
        for status in (
            Order.OrderStatus.CONFIRMED,
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.READY,
            Order.OrderStatus.COMPLETED,
        ):
            with self.subTest(status=status):
                response = self._post_status(status)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['data']['order']['status'], status)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.COMPLETED)

    def test_management_can_cancel_before_terminal_state(self):
        self.client.force_login(self.manager)
        response = self._post_status(Order.OrderStatus.CANCELLED)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['order']['status'], Order.OrderStatus.CANCELLED)

    def test_invalid_transition_rolls_back_status(self):
        self.client.force_login(self.manager)
        response = self._post_status(Order.OrderStatus.READY)
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)

        self._post_status(Order.OrderStatus.CONFIRMED)
        response = self._post_status(Order.OrderStatus.PENDING)
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)

    def test_terminal_orders_cannot_transition(self):
        self.client.force_login(self.manager)
        self.order.status = Order.OrderStatus.COMPLETED
        self.order.save()
        response = self._post_status(Order.OrderStatus.CANCELLED)
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.COMPLETED)

    def test_customer_cannot_update_any_order_status(self):
        self.client.force_login(self.customer)
        response = self._post_status(Order.OrderStatus.CONFIRMED)
        self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)

        other_order = Order.objects.create(
            order_number='LIFECYCLE-002',
            customer=self.other_customer,
            payment_method=Order.PaymentMethod.CASH,
        )
        response = self.client.post(
            f'/orders/{other_order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.CONFIRMED}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_status_endpoint_requires_authentication_and_management_role(self):
        self.assertEqual(self._post_status(Order.OrderStatus.CONFIRMED).status_code, 401)
        staff = User.objects.create_user(
            email='lifecycle-staff@example.com',
            username='lifecycle-staff',
            password='testpass123',
            role='STAFF',
        )
        self.client.force_login(staff)
        self.assertEqual(self._post_status(Order.OrderStatus.CONFIRMED).status_code, 200)

    def test_status_endpoint_404_and_405(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post('/orders/999999/status/', data='{}', content_type='application/json').status_code, 404)
        for method in ('get', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(f'/orders/{self.order.id}/status/').status_code, 405)

    def test_invalid_status_body_does_not_change_order(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            f'/orders/{self.order.id}/status/',
            data=json.dumps({'status': 'UNKNOWN'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)


class OrdersSalesIntegrationTests(TestCase):
    """Focused tests for confirmed Order conversion into completed Sales."""

    @classmethod
    def setUpTestData(cls):
        cls.category = ProductCategory.objects.create(name='Integration Category', slug='integration-category')
        cls.product = Product.objects.create(
            name='Integration Product',
            sku='INT-001',
            category=cls.category,
            selling_price=Decimal('1250.50'),
            cost_price=Decimal('800.00'),
        )
        cls.second_product = Product.objects.create(
            name='Second Integration Product',
            sku='INT-002',
            category=cls.category,
            selling_price=Decimal('300.00'),
            cost_price=Decimal('200.00'),
        )
        cls.customer = User.objects.create_user(
            email='integration-customer@example.com',
            username='integration-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.other_customer = User.objects.create_user(
            email='integration-other@example.com',
            username='integration-other',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.cashier = User.objects.create_user(
            email='integration-cashier@example.com',
            username='integration-cashier',
            password='testpass123',
            role='CASHIER',
        )
        cls.manager = User.objects.create_user(
            email='integration-manager@example.com',
            username='integration-manager',
            password='testpass123',
            role='MANAGER',
        )

    def setUp(self):
        self.client = Client()
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=5)
        self.second_inventory = InventoryItem.objects.create(product=self.second_product, quantity=4)
        self.order = Order.objects.create(
            order_number='INTEGRATION-001',
            customer=self.customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.CASH,
            subtotal=Decimal('2801.00'),
            total=Decimal('2801.00'),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('1250.50'),
            product_name_snapshot='Integration Product at order time',
            sku_snapshot='INT-OLD-001',
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.second_product,
            quantity=1,
            unit_price=Decimal('300.00'),
            product_name_snapshot='Second Integration Product',
            sku_snapshot='INT-002',
        )

    def _convert(self, order_id=None):
        return self.client.post(f'/orders/{order_id or self.order.id}/convert-to-sale/')

    def test_confirmed_order_converts_to_sale_with_snapshots_and_inventory_movement(self):
        self.client.force_login(self.manager)
        response = self._convert()
        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        sale = Sale.objects.get(source_order=self.order)
        self.assertEqual(self.order.status, Order.OrderStatus.COMPLETED)
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.COMPLETED)
        self.assertEqual(sale.customer, self.customer)
        self.assertEqual(sale.cashier, self.manager)
        self.assertEqual(sale.subtotal, self.order.subtotal)
        self.assertEqual(sale.total, self.order.total)
        sale_items = list(sale.items.order_by('id'))
        self.assertEqual(len(sale_items), 2)
        self.assertEqual(sale_items[0].unit_price, Decimal('1250.50'))
        self.assertEqual(sale_items[0].product_name_snapshot, 'Integration Product at order time')
        self.assertEqual(sale_items[0].sku_snapshot, 'INT-OLD-001')
        self.assertEqual(self.inventory.refresh_from_db(), None)
        self.assertEqual(self.inventory.quantity, 3)
        self.assertEqual(self.second_inventory.refresh_from_db(), None)
        self.assertEqual(self.second_inventory.quantity, 3)
        movements = StockMovement.objects.filter(reference=sale.sale_number).order_by('id')
        self.assertEqual(movements.count(), 2)
        self.assertTrue(all(movement.movement_type == StockMovement.MovementType.STOCK_OUT for movement in movements))

    def test_conversion_uses_order_price_after_product_price_changes(self):
        self.product.selling_price = Decimal('9999.99')
        self.product.save()
        self.client.force_login(self.cashier)
        self.assertEqual(self._convert().status_code, 200)
        sale_item = Sale.objects.get(source_order=self.order).items.get(product=self.product)
        self.assertEqual(sale_item.unit_price, Decimal('1250.50'))

    def test_duplicate_conversion_returns_409_without_extra_sale_or_movement(self):
        self.client.force_login(self.manager)
        self.assertEqual(self._convert().status_code, 200)
        sale_count = Sale.objects.count()
        movement_count = StockMovement.objects.count()
        response = self._convert()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Sale.objects.count(), sale_count)
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_only_confirmed_orders_can_convert(self):
        self.client.force_login(self.manager)
        for status in (Order.OrderStatus.PENDING, Order.OrderStatus.PROCESSING, Order.OrderStatus.READY, Order.OrderStatus.COMPLETED, Order.OrderStatus.CANCELLED):
            with self.subTest(status=status):
                self.order.status = status
                self.order.save()
                response = self._convert()
                self.assertEqual(response.status_code, 409)
                self.assertFalse(Sale.objects.filter(source_order=self.order).exists())

    def test_customer_and_unauthorized_roles_cannot_convert(self):
        self.client.force_login(self.customer)
        self.assertEqual(self._convert().status_code, 403)
        self.client.force_login(self.other_customer)
        self.assertEqual(self._convert().status_code, 403)
        staff = User.objects.create_user(email='integration-staff@example.com', username='integration-staff', password='testpass123', role='STAFF')
        self.client.force_login(staff)
        self.assertEqual(self._convert().status_code, 403)

    def test_missing_order_and_unsupported_methods(self):
        self.client.force_login(self.manager)
        self.assertEqual(self._convert(order_id=999999).status_code, 404)
        for method in ('get', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(f'/orders/{self.order.id}/convert-to-sale/').status_code, 405)

    def test_insufficient_stock_rolls_back_sale_order_and_inventory(self):
        self.inventory.quantity = 1
        self.inventory.save()
        self.client.force_login(self.manager)
        response = self._convert()
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.inventory.quantity, 1)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_sale_creation_error_rolls_back_all_changes(self):
        self.client.force_login(self.manager)
        with patch(
            'apps.orders.views.SaleItem.objects.create',
            side_effect=ValidationError({'items': 'Sale item could not be created.'}),
        ):
            response = self._convert()
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.inventory.quantity, 5)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)


class OrdersNotificationTrackingTests(TestCase):
    """Focused tests for Order events recorded by Notifications."""

    @classmethod
    def setUpTestData(cls):
        cls.category = ProductCategory.objects.create(
            name='Notification Category',
            slug='notification-category',
        )
        cls.product = Product.objects.create(
            name='Notification Product',
            sku='NOTIFY-001',
            category=cls.category,
            selling_price=Decimal('100.00'),
            cost_price=Decimal('50.00'),
        )
        cls.customer = User.objects.create_user(
            email='notification-customer@example.com',
            username='notification-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.manager = User.objects.create_user(
            email='notification-manager@example.com',
            username='notification-manager',
            password='testpass123',
            role='MANAGER',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.customer)

    def _create_order(self):
        return self.client.post(
            '/orders/',
            data=json.dumps({
                'items': [{'product_id': self.product.id, 'quantity': 2}],
            }),
            content_type='application/json',
        )

    def test_order_creation_notifies_active_management_with_related_order(self):
        response = self._create_order()
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        order_content_type = ContentType.objects.get_for_model(Order)
        notification = Notification.objects.get(
            recipient=self.manager,
            content_type=order_content_type,
            object_id=str(order.id),
        )
        self.assertEqual(notification.notification_type, Notification.NotificationType.ORDER)
        self.assertEqual(notification.priority, Notification.Priority.HIGH)
        self.assertEqual(notification.title, 'New customer order')
        self.assertEqual(notification.action_url, f'/orders/{order.id}/')

    def test_invalid_order_does_not_create_notification(self):
        response = self.client.post(
            '/orders/',
            data=json.dumps({'items': [{'product_id': 999999, 'quantity': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Notification.objects.count(), 0)

    def test_status_update_notifies_customer_after_successful_change(self):
        self.client.force_login(self.customer)
        response = self._create_order()
        order = Order.objects.get()
        self.client.force_login(self.manager)
        response = self.client.post(
            f'/orders/{order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.CONFIRMED}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        order_content_type = ContentType.objects.get_for_model(Order)
        notification = Notification.objects.get(
            recipient=self.customer,
            content_type=order_content_type,
            object_id=str(order.id),
            title='Order status updated',
        )
        self.assertIn('Confirmed', notification.message)

    def test_invalid_status_does_not_notify_customer(self):
        self.client.force_login(self.customer)
        self._create_order()
        order = Order.objects.get()
        self.client.force_login(self.manager)
        response = self.client.post(
            f'/orders/{order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.READY}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Notification.objects.filter(recipient=self.customer).exists())

    def test_successful_order_to_sale_notifies_customer(self):
        InventoryItem.objects.create(product=self.product, quantity=2)
        order = Order.objects.create(
            order_number='NOTIFY-CONVERT-001',
            customer=self.customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.CASH,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot='Notification Product',
            sku_snapshot='NOTIFY-001',
        )
        self.client.force_login(self.manager)
        response = self.client.post(f'/orders/{order.id}/convert-to-sale/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Notification.objects.filter(
            recipient=self.customer,
            title='Order completed',
            object_id=str(order.id),
        ).exists())


class OrdersManagementApiTests(TestCase):
    """Focused management workflow tests for Orders APIs."""

    @classmethod
    def setUpTestData(cls):
        cls.category = ProductCategory.objects.create(name='Management Category', slug='management-category')
        cls.product = Product.objects.create(
            name='Management Product',
            sku='MGMT-001',
            category=cls.category,
            selling_price=Decimal('100.00'),
            cost_price=Decimal('50.00'),
        )
        cls.customer = User.objects.create_user(
            email='management-customer@example.com',
            username='management-customer',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.other_customer = User.objects.create_user(
            email='management-other@example.com',
            username='management-other',
            password='testpass123',
            role='CUSTOMER',
        )
        cls.manager = User.objects.create_user(
            email='management-manager@example.com',
            username='management-manager',
            password='testpass123',
            role='MANAGER',
        )

    def setUp(self):
        self.client = Client()
        self.customer_order = Order.objects.create(
            order_number='MGMT-CUSTOMER',
            customer=self.customer,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.CASH,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )
        self.other_order = Order.objects.create(
            order_number='MGMT-OTHER',
            customer=self.other_customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.CARD,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
        )
        OrderItem.objects.create(
            order=self.customer_order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot='Management Product',
            sku_snapshot='MGMT-001',
        )
        InventoryItem.objects.create(product=self.product, quantity=5)

    def test_only_management_roles_can_use_management_operations(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/orders/').status_code, 200)
        self.assertEqual(self.client.post(f'/orders/{self.customer_order.id}/status/', data=json.dumps({'status': 'CONFIRMED'}), content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(f'/orders/{self.customer_order.id}/convert-to-sale/').status_code, 403)

    def test_management_list_filters_and_pagination(self):
        self.client.force_login(self.manager)
        response = self.client.get('/orders/?customer={}&payment_method=CASH&status=PENDING&page=1&page_size=1&search=MGMT'.format(self.customer.id))
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['pagination']['total_count'], 1)
        self.assertEqual(data['orders'][0]['order_number'], 'MGMT-CUSTOMER')
        self.assertEqual(self.client.get('/orders/?customer=not-a-number').status_code, 400)

    def test_customer_cannot_bypass_isolation_with_management_filters(self):
        self.client.force_login(self.customer)
        response = self.client.get(f'/orders/?customer={self.other_customer.id}&search=MGMT-OTHER')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['pagination']['total_count'], 0)

    def test_management_can_progress_and_cancel_orders(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            f'/orders/{self.customer_order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.CONFIRMED}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            f'/orders/{self.customer_order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.CANCELLED}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.customer_order.refresh_from_db()
        self.assertEqual(self.customer_order.status, Order.OrderStatus.CANCELLED)

    def test_invalid_transition_preserves_status_and_notifications(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            f'/orders/{self.customer_order.id}/status/',
            data=json.dumps({'status': Order.OrderStatus.READY}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.customer_order.refresh_from_db()
        self.assertEqual(self.customer_order.status, Order.OrderStatus.PENDING)
        self.assertFalse(Notification.objects.filter(
            content_type=ContentType.objects.get_for_model(Order),
            object_id=str(self.customer_order.id),
        ).exists())

    def test_confirmed_order_conversion_and_duplicate_protection(self):
        self.client.force_login(self.manager)
        response = self.client.post(f'/orders/{self.other_order.id}/convert-to-sale/')
        self.assertEqual(response.status_code, 400)
        OrderItem.objects.create(
            order=self.other_order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot='Management Product',
            sku_snapshot='MGMT-001',
        )
        response = self.client.post(f'/orders/{self.other_order.id}/convert-to-sale/')
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f'/orders/{self.other_order.id}/convert-to-sale/')
        self.assertEqual(response.status_code, 409)

    def test_management_detail_and_unsupported_methods(self):
        self.client.force_login(self.manager)
        response = self.client.get(f'/orders/{self.customer_order.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['order']['customer']['id'], self.customer.id)
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(f'/orders/{self.customer_order.id}/').status_code, 405)
        self.assertEqual(self.client.get('/orders/999999/').status_code, 404)
