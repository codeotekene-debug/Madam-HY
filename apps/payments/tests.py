from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.inventory.models import InventoryItem
from apps.orders.models import Order
from apps.products.models import Product, ProductCategory
from apps.sales.models import Sale
from .models import Payment


class PaymentModelTests(TestCase):
    """Test Payment model creation and validation."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            username='customer1',
            email='customer1@example.com',
            password='StrongPass123',
            role='CUSTOMER',
            first_name='Jane',
            last_name='Doe',
        )
        cls.cashier = User.objects.create_user(
            username='cashier1',
            email='cashier1@example.com',
            password='StrongPass123',
            role='CASHIER',
            first_name='Grace',
            last_name='Smith',
        )
        cls.category = ProductCategory.objects.create(name='Fashion', slug='fashion')
        cls.product = Product.objects.create(
            name='Test Product',
            slug='test-product',
            sku='TST-001',
            category=cls.category,
            selling_price=Decimal('15000.00'),
            cost_price=Decimal('9000.00'),
        )
        InventoryItem.objects.create(product=cls.product, quantity=50)

    def test_payment_creation_with_sale_relationship(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('2000.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-001',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('2000.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-CASH-001',
            notes='Cash payment received',
        )
        self.assertEqual(payment.sale, sale)
        self.assertEqual(payment.amount, Decimal('2000.00'))
        self.assertEqual(payment.payment_method, Payment.PaymentMethod.CASH)

    def test_payment_creation_with_order_relationship(self):
        order = Order.objects.create(
            order_number='MH-ORD-20001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CARD,
            total=Decimal('2500.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-002',
            order=order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('2500.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-CARD-001',
        )
        self.assertEqual(payment.order, order)
        self.assertEqual(payment.customer, self.customer)

    def test_payment_reference_must_be_unique(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-002',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('1500.00'),
        )
        Payment.objects.create(
            payment_reference='PMT-UNIQUE-1',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('1500.00'),
            payment_method=Payment.PaymentMethod.CASH,
        )

        with self.assertRaises(ValidationError):
            duplicate = Payment(
                payment_reference='PMT-UNIQUE-1',
                sale=sale,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('1500.00'),
                payment_method=Payment.PaymentMethod.CASH,
            )
            duplicate.full_clean()

    def test_payment_method_choices_are_valid(self):
        methods = [
            Payment.PaymentMethod.CASH,
            Payment.PaymentMethod.BANK_TRANSFER,
            Payment.PaymentMethod.CARD,
            Payment.PaymentMethod.CREDIT,
        ]
        for index, method in enumerate(methods, start=1):
            sale = Sale.objects.create(
                sale_number=f'MH-SALE-{100 + index}',
                customer=self.customer,
                cashier=self.cashier,
                payment_method=Sale.PaymentMethod.CASH,
                total=Decimal('1000.00'),
            )
            payment = Payment.objects.create(
                payment_reference=f'PMT-METHOD-{index}',
                sale=sale,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('1000.00'),
                payment_method=method,
                payment_status=Payment.PaymentStatus.COMPLETED,
            )
            self.assertEqual(payment.payment_method, method)

    def test_payment_status_choices_are_valid(self):
        statuses = [
            Payment.PaymentStatus.PENDING,
            Payment.PaymentStatus.COMPLETED,
            Payment.PaymentStatus.FAILED,
            Payment.PaymentStatus.REFUNDED,
        ]
        for index, status in enumerate(statuses, start=1):
            sale = Sale.objects.create(
                sale_number=f'MH-SALE-{200 + index}',
                customer=self.customer,
                cashier=self.cashier,
                payment_method=Sale.PaymentMethod.CASH,
                total=Decimal('1200.00'),
            )
            payment = Payment.objects.create(
                payment_reference=f'PMT-STATUS-{index}',
                sale=sale,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('1200.00'),
                payment_method=Payment.PaymentMethod.CASH,
                payment_status=status,
            )
            self.assertEqual(payment.payment_status, status)

    def test_payment_amount_must_be_positive(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-003',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('500.00'),
        )
        with self.assertRaises(ValidationError):
            Payment(
                payment_reference='PMT-ZERO',
                sale=sale,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('0.00'),
                payment_method=Payment.PaymentMethod.CASH,
            ).full_clean()

        with self.assertRaises(ValidationError):
            Payment(
                payment_reference='PMT-NEGATIVE',
                sale=sale,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('-50.00'),
                payment_method=Payment.PaymentMethod.CASH,
            ).full_clean()

    def test_payment_requires_sale_or_order(self):
        with self.assertRaises(ValidationError):
            Payment(
                payment_reference='PMT-NO-RELATION',
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('100.00'),
                payment_method=Payment.PaymentMethod.CASH,
            ).full_clean()

    def test_payment_cannot_link_to_both_sale_and_order(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-004',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('600.00'),
        )
        order = Order.objects.create(
            order_number='MH-ORD-20002',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('600.00'),
        )
        with self.assertRaises(ValidationError):
            Payment(
                payment_reference='PMT-BOTH-RELATIONS',
                sale=sale,
                order=order,
                customer=self.customer,
                cashier=self.cashier,
                amount=Decimal('600.00'),
                payment_method=Payment.PaymentMethod.CASH,
            ).full_clean()

    def test_payment_transaction_metadata_records_reference_data(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-005',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CARD,
            total=Decimal('5000.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-META',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('5000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='AUTH-928341',
            transaction_metadata={'card_brand': 'visa', 'last4': '4242'},
        )
        self.assertEqual(payment.transaction_reference, 'AUTH-928341')
        self.assertEqual(payment.transaction_metadata['card_brand'], 'visa')
        self.assertEqual(payment.transaction_metadata['last4'], '4242')

    def test_completed_payment_is_protected_from_deletion(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-006',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('200.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-PROTECTED',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('200.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        with self.assertRaises(ValidationError):
            payment.delete()

    def test_payment_does_not_modify_inventory(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-007',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('3000.00'),
        )
        product_inventory = InventoryItem.objects.get(product=self.product)
        before_quantity = product_inventory.quantity

        Payment.objects.create(
            payment_reference='PMT-INVENTORY-CHECK',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('3000.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        product_inventory.refresh_from_db()
        self.assertEqual(product_inventory.quantity, before_quantity)

    def test_payment_does_not_modify_sale_total_or_order_total(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-008',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('900.00'),
        )
        order = Order.objects.create(
            order_number='MH-ORD-20003',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CARD,
            total=Decimal('1550.00'),
        )

        Payment.objects.create(
            payment_reference='PMT-SALE-UNCHANGED',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('900.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='PMT-ORDER-UNCHANGED',
            order=order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('1550.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        sale.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(sale.total, Decimal('900.00'))
        self.assertEqual(order.total, Decimal('1550.00'))

    def test_credit_payment_does_not_add_credit_accounting_logic(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-009',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('4500.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-CREDIT',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('4500.00'),
            payment_method=Payment.PaymentMethod.CREDIT,
            payment_status=Payment.PaymentStatus.PENDING,
        )
        self.assertEqual(payment.payment_method, Payment.PaymentMethod.CREDIT)
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)

    def test_decimal_precision_is_preserved(self):
        sale = Sale.objects.create(
            sale_number='MH-SALE-010',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('15125.99'),
        )
        payment = Payment.objects.create(
            payment_reference='PMT-DECIMAL',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('15125.99'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        self.assertEqual(payment.amount, Decimal('15125.99'))


class DjangoSystemChecksTests(TestCase):
    """Test Django system checks pass for Payments app."""

    def test_payments_app_checks_pass(self):
        out = __import__('io').StringIO()
        call_command('check', stdout=out)
        output = out.getvalue()
        self.assertNotIn('error', output.lower())
