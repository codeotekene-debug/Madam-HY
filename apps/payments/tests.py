import hashlib
import hmac
import json
import os
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.inventory.models import InventoryItem
from apps.orders.models import Order, OrderItem
from apps.products.models import Product, ProductCategory
from apps.sales.models import Sale, SaleItem
from .models import Payment
from .services import PaymentService
from .verification import (
    BasePaymentVerifier,
    InternalPaymentVerifier,
    MockPaymentVerifier,
    MoniepointPaymentVerifier,
    PaystackPaymentVerifier,
    PaymentVerificationResult,
    PaymentVerificationService,
    PaymentVerificationStatus,
    verify_payment_transaction,
)


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


class PaymentApiTests(TestCase):
    """Test the minimal safe Payments API slice."""

    def setUp(self):
        self.category = ProductCategory.objects.create(name='API Payments', slug='api-payments')
        self.product = Product.objects.create(
            name='API Payment Product',
            slug='api-payment-product',
            sku='PAY-001',
            category=self.category,
            selling_price=Decimal('150.00'),
            cost_price=Decimal('90.00'),
        )
        InventoryItem.objects.create(product=self.product, quantity=20)

        self.owner = User.objects.create_user(
            username='owner-pay', email='owner-pay@example.com', password='StrongPass123', role='OWNER',
            first_name='Owner', last_name='Pay'
        )
        self.manager = User.objects.create_user(
            username='manager-pay', email='manager-pay@example.com', password='StrongPass123', role='MANAGER',
            first_name='Manager', last_name='Pay'
        )
        self.cashier = User.objects.create_user(
            username='cashier-pay', email='cashier-pay@example.com', password='StrongPass123', role='CASHIER',
            first_name='Cashier', last_name='Pay'
        )
        self.customer = User.objects.create_user(
            username='customer-pay', email='customer-pay@example.com', password='StrongPass123', role='CUSTOMER',
            first_name='Customer', last_name='Pay'
        )
        self.other_customer = User.objects.create_user(
            username='other-customer-pay', email='other-customer-pay@example.com', password='StrongPass123', role='CUSTOMER',
            first_name='Other', last_name='Customer'
        )

        self.sale = Sale.objects.create(
            sale_number='PAY-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('150.00'),
            subtotal=Decimal('150.00'),
            amount_received=Decimal('150.00'),
            change_amount=Decimal('0.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        self.order = Order.objects.create(
            order_number='PAY-ORD-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('220.00'),
            subtotal=Decimal('220.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )

        self.payment = Payment.objects.create(
            payment_reference='PAY-REF-001',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('150.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-001',
        )

    def test_payments_list_requires_authentication_and_filters_customer_scope(self):
        response = self.client.get('/payments/')
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.customer)
        response = self.client.get('/payments/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']
        self.assertEqual(payload['pagination']['total_count'], 1)

        self.client.force_login(self.other_customer)
        response = self.client.get('/payments/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['pagination']['total_count'], 0)

    def test_staff_can_create_payment_for_sale_or_order(self):
        self.client.force_login(self.owner)
        payload = {
            'sale_id': self.sale.id,
            'customer_id': self.customer.id,
            'cashier_id': self.cashier.id,
            'amount': '200.00',
            'payment_method': 'CASH',
            'payment_status': 'PENDING',
            'transaction_reference': 'TXN-NEW-001',
            'notes': 'Cash payment recorded via API',
        }
        response = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        self.assertEqual(data['payment_reference'][:4], 'PMT-')
        self.assertEqual(data['amount'], '200.00')
        self.assertEqual(data['customer']['id'], self.customer.id)

    def test_payment_create_validates_mutually_exclusive_transaction_and_amount(self):
        self.client.force_login(self.manager)
        invalid_payloads = [
            {'sale_id': self.sale.id, 'order_id': self.order.id, 'amount': '100.00', 'payment_method': 'CASH'},
            {'amount': '0.00', 'payment_method': 'CASH', 'sale_id': self.sale.id},
            {'amount': '-50.00', 'payment_method': 'CASH', 'sale_id': self.sale.id},
            {'payment_method': 'INVALID', 'sale_id': self.sale.id, 'amount': '100.00'},
            {'customer_id': self.other_customer.id, 'sale_id': self.sale.id, 'amount': '100.00', 'payment_method': 'CASH'},
        ]

        for payload in invalid_payloads:
            response = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json')
            self.assertEqual(response.status_code, 400, msg=payload)

    def test_payment_detail_requires_authorization_and_404s(self):
        self.client.force_login(self.customer)
        response = self.client.get(f'/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['payment_reference'], 'PAY-REF-001')

        self.client.force_login(self.other_customer)
        response = self.client.get(f'/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.get('/payments/999999/')
        self.assertEqual(response.status_code, 404)

    def test_payment_api_rejects_unsupported_methods(self):
        self.client.force_login(self.owner)
        response = self.client.post(f'/payments/{self.payment.id}/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 405)

    def test_idempotent_sale_payment_retry_returns_existing_payment(self):
        self.client.force_login(self.owner)
        payload = {
            'sale_id': self.sale.id,
            'customer_id': self.customer.id,
            'cashier_id': self.cashier.id,
            'amount': '200.00',
            'payment_method': 'TRANSFER',
            'payment_status': 'PENDING',
            'transaction_reference': 'IDEMP-SALE-TXN',
        }
        before_count = Payment.objects.count()
        headers = {'HTTP_X_IDEMPOTENCY_KEY': 'idemp-sale-001'}
        first = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json', **headers)
        second = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json', **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()['data']['id'], second.json()['data']['id'])
        self.assertEqual(Payment.objects.count(), before_count + 1)

    def test_idempotency_key_rejects_conflicting_payment_data(self):
        self.client.force_login(self.owner)
        headers = {'HTTP_X_IDEMPOTENCY_KEY': 'idemp-conflict-001'}
        base_payload = {
            'sale_id': self.sale.id,
            'customer_id': self.customer.id,
            'cashier_id': self.cashier.id,
            'amount': '200.00',
            'payment_method': 'CASH',
            'payment_status': 'PENDING',
        }
        first = self.client.post('/payments/', data=json.dumps(base_payload), content_type='application/json', **headers)
        self.assertEqual(first.status_code, 201)

        for conflict in (
            {'amount': '201.00'},
            {'payment_method': 'CARD'},
            {'order_id': self.order.id, 'sale_id': None},
        ):
            payload = {**base_payload, **conflict}
            response = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json', **headers)
            self.assertEqual(response.status_code, 400, msg=conflict)

        self.assertEqual(Payment.objects.filter(idempotency_key='idemp-conflict-001').count(), 1)

    def test_idempotent_order_payment_and_different_keys_work(self):
        self.client.force_login(self.owner)
        payload = {
            'order_id': self.order.id,
            'customer_id': self.customer.id,
            'cashier_id': self.cashier.id,
            'amount': '220.00',
            'payment_method': 'TRANSFER',
            'payment_status': 'PENDING',
        }
        headers = {'HTTP_X_IDEMPOTENCY_KEY': 'idemp-order-001'}
        first = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json', **headers)
        second = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json', **headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()['data']['id'], second.json()['data']['id'])
        self.assertEqual(first.json()['data']['payment_method'], Payment.PaymentMethod.BANK_TRANSFER)

        distinct = self.client.post(
            '/payments/',
            data=json.dumps({**payload, 'amount': '10.00'}),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY='idemp-order-002',
        )
        self.assertEqual(distinct.status_code, 201)

    def test_idempotency_key_requires_valid_length_and_authorization(self):
        payload = {
            'sale_id': self.sale.id,
            'amount': '10.00',
            'payment_method': 'CASH',
        }
        unauthenticated = self.client.post(
            '/payments/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY='idemp-auth-001',
        )
        self.assertEqual(unauthenticated.status_code, 401)

        self.client.force_login(self.owner)
        response = self.client.post(
            '/payments/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY='x' * 121,
        )
        self.assertEqual(response.status_code, 400)

    def create_pending_payment(self, *, sale=None, order=None, reference='CONFIRM-PENDING'):
        return Payment.objects.create(
            payment_reference=reference,
            sale=sale,
            order=order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('50.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.PENDING,
        )

    def test_confirmation_completes_pending_payment_and_records_audit(self):
        payment = self.create_pending_payment(sale=self.sale)
        self.client.force_login(self.manager)

        response = self.client.post(f'/payments/{payment.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['payment_status'], Payment.PaymentStatus.COMPLETED)
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)
        audit = ActivityLog.objects.get(object_id=str(payment.id), action_type=ActivityLog.ActionType.PAYMENT)
        self.assertEqual(audit.actor, self.manager)
        self.assertEqual(audit.action_type, ActivityLog.ActionType.PAYMENT)
        self.assertIsNotNone(audit.created_at)

    def test_completed_confirmation_is_idempotent_without_duplicate_audit(self):
        self.client.force_login(self.owner)
        before_count = Payment.objects.count()
        first = self.client.post(f'/payments/{self.payment.id}/confirm/')
        second = self.client.post(f'/payments/{self.payment.id}/confirm/')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['data']['id'], self.payment.id)
        self.assertEqual(second.json()['data']['id'], self.payment.id)
        self.assertEqual(Payment.objects.count(), before_count)
        self.assertEqual(ActivityLog.objects.filter(action_type=ActivityLog.ActionType.PAYMENT).count(), 0)

    def test_failed_and_refunded_payments_cannot_be_confirmed(self):
        failed = Payment.objects.create(
            payment_reference='CONFIRM-FAILED', sale=self.sale, customer=self.customer,
            cashier=self.cashier, amount=Decimal('50.00'), payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.FAILED,
        )
        refunded = Payment.objects.create(
            payment_reference='CONFIRM-REFUNDED', sale=self.sale, customer=self.customer,
            cashier=self.cashier, amount=Decimal('50.00'), payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.REFUNDED,
        )
        self.client.force_login(self.owner)

        self.assertEqual(self.client.post(f'/payments/{failed.id}/confirm/').status_code, 400)
        self.assertEqual(self.client.post(f'/payments/{refunded.id}/confirm/').status_code, 400)
        failed.refresh_from_db()
        refunded.refresh_from_db()
        self.assertEqual(failed.payment_status, Payment.PaymentStatus.FAILED)
        self.assertEqual(refunded.payment_status, Payment.PaymentStatus.REFUNDED)

    def test_only_owner_and_manager_can_confirm_payments(self):
        payment = self.create_pending_payment(sale=self.sale, reference='CONFIRM-AUTH')
        staff = User.objects.create_user(
            username='confirm-staff', email='confirm-staff@example.com', password='StrongPass123', role='STAFF'
        )

        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(f'/payments/{payment.id}/confirm/').status_code, 403)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(f'/payments/{payment.id}/confirm/').status_code, 403)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(f'/payments/{payment.id}/confirm/').status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(f'/payments/{payment.id}/confirm/').status_code, 200)

    def test_confirmation_updates_balance_without_mutating_order_or_creating_payment(self):
        payment = self.create_pending_payment(order=self.order, reference='CONFIRM-BALANCE')
        before_count = Payment.objects.count()
        original_status = self.order.status
        original_payment_status = self.order.payment_status
        original_total = self.order.total
        self.client.force_login(self.owner)

        response = self.client.post(f'/payments/{payment.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        balance = PaymentService.get_transaction_balance(self.order)
        self.assertEqual(balance['completed_amount'], Decimal('50.00'))
        self.assertEqual(balance['pending_amount'], Decimal('0.00'))
        self.assertEqual(balance['outstanding_amount'], Decimal('170.00'))
        self.assertEqual(balance['overpaid_amount'], Decimal('0.00'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, original_status)
        self.assertEqual(self.order.payment_status, original_payment_status)
        self.assertEqual(self.order.total, original_total)
        self.assertEqual(Payment.objects.count(), before_count)

    def test_confirmation_does_not_mutate_sale_or_inventory(self):
        payment = self.create_pending_payment(sale=self.sale, reference='CONFIRM-SALE')
        original_sale = (self.sale.status, self.sale.payment_status, self.sale.amount_received, self.sale.change_amount)
        inventory = InventoryItem.objects.get(product=self.product)
        original_quantity = inventory.quantity
        self.client.force_login(self.manager)

        response = self.client.post(f'/payments/{payment.id}/confirm/')

        self.assertEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual((self.sale.status, self.sale.payment_status, self.sale.amount_received, self.sale.change_amount), original_sale)
        self.assertEqual(inventory.quantity, original_quantity)
        self.assertEqual(Payment.objects.filter(sale=self.sale).count(), 2)

    def test_creation_rejects_client_supplied_completed_status(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            '/payments/',
            data=json.dumps({
                'sale_id': self.sale.id,
                'customer_id': self.customer.id,
                'cashier_id': self.cashier.id,
                'amount': '10.00',
                'payment_method': 'CASH',
                'payment_status': 'COMPLETED',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.filter(sale=self.sale).count(), 1)

    def test_reconciliation_requires_authentication_and_management_role(self):
        order_url = f'/payments/reconciliation/order/{self.order.id}/'
        sale_url = f'/payments/reconciliation/sale/{self.sale.id}/'
        self.assertEqual(self.client.get(order_url).status_code, 401)
        self.assertEqual(self.client.get(sale_url).status_code, 401)

        for role in ('CUSTOMER', 'CASHIER', 'STAFF'):
            user = self.customer if role == 'CUSTOMER' else self.cashier
            if role == 'STAFF':
                user = User.objects.create_user(
                    username='reconcile-staff', email='reconcile-staff@example.com', password='StrongPass123', role=role
                )
            self.client.force_login(user)
            self.assertEqual(self.client.get(order_url).status_code, 403)
            self.assertEqual(self.client.get(sale_url).status_code, 403)

    def test_owner_and_manager_can_reconcile_order_and_sale(self):
        for user in (self.owner, self.manager):
            self.client.force_login(user)
            self.assertEqual(self.client.get(f'/payments/reconciliation/order/{self.order.id}/').status_code, 200)
            self.assertEqual(self.client.get(f'/payments/reconciliation/sale/{self.sale.id}/').status_code, 200)

    def test_reconciliation_returns_order_balance_counts_and_decimal_strings(self):
        Payment.objects.create(
            payment_reference='RECON-ORDER-COMPLETED', order=self.order, customer=self.customer,
            cashier=self.cashier, amount=Decimal('100.00'), payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='RECON-ORDER-PENDING', order=self.order, customer=self.customer,
            cashier=self.cashier, amount=Decimal('50.00'), payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.PENDING,
        )
        self.client.force_login(self.owner)
        response = self.client.get(f'/payments/reconciliation/order/{self.order.id}/')

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['transaction_type'], 'ORDER')
        self.assertEqual(data['transaction_id'], self.order.id)
        self.assertEqual(data['transaction_identifier'], self.order.order_number)
        self.assertEqual(data['payment_count'], 2)
        self.assertEqual(data['completed_payment_count'], 1)
        self.assertEqual(data['pending_payment_count'], 1)
        self.assertEqual(data['completed_amount'], '100.00')
        self.assertEqual(data['pending_amount'], '50.00')
        self.assertEqual(data['outstanding_amount'], '120.00')
        self.assertEqual(data['overpaid_amount'], '0.00')
        self.assertEqual(data['classification'], 'PARTIALLY_PAID')

    def test_reconciliation_returns_sale_balance_and_inconsistency_findings(self):
        Payment.objects.create(
            payment_reference='RECON-SALE-MISMATCH', sale=self.sale, customer=self.other_customer,
            cashier=self.cashier, amount=Decimal('200.00'), payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED, transaction_reference='DUP-RECON',
        )
        Payment.objects.create(
            payment_reference='RECON-SALE-DUPLICATE', sale=self.sale, customer=self.customer,
            cashier=self.cashier, amount=Decimal('1.00'), payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING, transaction_reference='DUP-RECON',
        )
        self.client.force_login(self.manager)
        response = self.client.get(f'/payments/reconciliation/sale/{self.sale.id}/')

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['transaction_type'], 'SALE')
        self.assertEqual(data['completed_amount'], '350.00')
        self.assertEqual(data['classification'], 'OVERPAID')
        self.assertIn('COMPLETED_PAYMENT_EXCEEDS_TRANSACTION_TOTAL', data['inconsistency_findings'])
        self.assertIn('PAYMENT_CUSTOMER_MISMATCH', data['inconsistency_findings'])
        self.assertIn('DUPLICATE_TRANSACTION_REFERENCE', data['inconsistency_findings'])

    def test_reconciliation_is_read_only_and_get_only(self):
        before_order = (self.order.status, self.order.payment_status, self.order.total)
        before_sale = (self.sale.status, self.sale.payment_status, self.sale.total, self.sale.amount_received, self.sale.change_amount)
        before_payments = list(Payment.objects.values_list('id', 'payment_status', 'amount'))
        before_activity_count = ActivityLog.objects.count()
        self.client.force_login(self.owner)

        response = self.client.get(f'/payments/reconciliation/order/{self.order.id}/')

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual((self.order.status, self.order.payment_status, self.order.total), before_order)
        self.assertEqual((self.sale.status, self.sale.payment_status, self.sale.total, self.sale.amount_received, self.sale.change_amount), before_sale)
        self.assertEqual(list(Payment.objects.values_list('id', 'payment_status', 'amount')), before_payments)
        self.assertEqual(ActivityLog.objects.count(), before_activity_count)

        url = f'/payments/reconciliation/order/{self.order.id}/'
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_reconciliation_not_found_and_invalid_ids_return_json_errors(self):
        self.client.force_login(self.owner)
        invalid_ids = ['999999', 'not-an-id', '-1', '0', 'abc123xyz', '12.34']
        for test_id in invalid_ids:
            for entity in ('order', 'sale'):
                url = f'/payments/reconciliation/{entity}/{test_id}/'
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404, msg=f'Failed for {url}')
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], f'{entity.capitalize()} not found.')

    def test_reconciliation_all_classification_states(self):
        self.client.force_login(self.owner)

        # 1. UNPAID state
        unpaid_order = Order.objects.create(
            order_number='RECON-UNPAID-ORD',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Order.PaymentStatus.PENDING,
            status=Order.OrderStatus.PENDING,
        )
        resp = self.client.get(f'/payments/reconciliation/order/{unpaid_order.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['classification'], 'UNPAID')
        self.assertEqual(resp.json()['data']['completed_amount'], '0.00')
        self.assertEqual(resp.json()['data']['outstanding_amount'], '100.00')

        # 2. PARTIALLY_PAID state
        part_order = Order.objects.create(
            order_number='RECON-PART-ORD',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )
        Payment.objects.create(
            payment_reference='PMT-RECON-PART',
            order=part_order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('40.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        resp = self.client.get(f'/payments/reconciliation/order/{part_order.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['classification'], 'PARTIALLY_PAID')
        self.assertEqual(resp.json()['data']['completed_amount'], '40.00')
        self.assertEqual(resp.json()['data']['outstanding_amount'], '60.00')

        # 3. FULLY_PAID state
        full_sale = Sale.objects.create(
            sale_number='RECON-FULL-SALE',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='PMT-RECON-FULL',
            sale=full_sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('100.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        resp = self.client.get(f'/payments/reconciliation/sale/{full_sale.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['classification'], 'FULLY_PAID')
        self.assertEqual(resp.json()['data']['completed_amount'], '100.00')
        self.assertEqual(resp.json()['data']['outstanding_amount'], '0.00')

        # 4. OVERPAID state
        over_sale = Sale.objects.create(
            sale_number='RECON-OVER-SALE',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='PMT-RECON-OVER',
            sale=over_sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('150.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        resp = self.client.get(f'/payments/reconciliation/sale/{over_sale.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['classification'], 'OVERPAID')
        self.assertEqual(resp.json()['data']['completed_amount'], '150.00')
        self.assertEqual(resp.json()['data']['overpaid_amount'], '50.00')


class PaymentServiceTests(TestCase):
    """Test the Payment service layer contracts without changing Orders or Sales behavior."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='service-customer',
            email='service-customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
            first_name='Service',
            last_name='Customer',
        )
        self.cashier = User.objects.create_user(
            username='service-cashier',
            email='service-cashier@example.com',
            password='StrongPass123',
            role='CASHIER',
            first_name='Cash',
            last_name='ier',
        )
        self.owner = User.objects.create_user(
            username='service-owner',
            email='service-owner@example.com',
            password='StrongPass123',
            role='OWNER',
            first_name='Service',
            last_name='Owner',
        )
        self.category = ProductCategory.objects.create(name='Service Payments', slug='service-payments')
        self.product = Product.objects.create(
            name='Service Payment Product',
            slug='service-payment-product',
            sku='SERVICE-PAY-001',
            category=self.category,
            selling_price=Decimal('200.00'),
            cost_price=Decimal('120.00'),
        )
        InventoryItem.objects.create(product=self.product, quantity=5)
        self.sale = Sale.objects.create(
            sale_number='SERVICE-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('200.00'),
            subtotal=Decimal('200.00'),
            amount_received=Decimal('200.00'),
            change_amount=Decimal('0.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        self.order = Order.objects.create(
            order_number='SERVICE-ORD-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.TRANSFER,
            total=Decimal('250.00'),
            subtotal=Decimal('250.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )

    def test_service_creates_valid_payment(self):
        payment = PaymentService.create_payment(
            payment_reference='PMT-SERVICE-001',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount='200.00',
            payment_method='CASH',
            payment_status='COMPLETED',
            transaction_reference='TXN-001',
            allow_completed=True,
        )

        self.assertEqual(payment.amount, Decimal('200.00'))
        self.assertEqual(payment.payment_method, Payment.PaymentMethod.CASH)
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertEqual(payment.sale_id, self.sale.id)

    def test_service_rejects_invalid_amount(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-1',
                sale=self.sale,
                customer=self.customer,
                cashier=self.cashier,
                amount='-5.00',
                payment_method='CASH',
            )

    def test_service_requires_sale_or_order(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-2',
                customer=self.customer,
                cashier=self.cashier,
                amount='10.00',
                payment_method='CASH',
            )

    def test_service_rejects_both_sale_and_order(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-3',
                sale=self.sale,
                order=self.order,
                customer=self.customer,
                cashier=self.cashier,
                amount='10.00',
                payment_method='CASH',
            )

    def test_service_rejects_invalid_payment_method(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-4',
                sale=self.sale,
                customer=self.customer,
                cashier=self.cashier,
                amount='10.00',
                payment_method='NOT_REAL',
            )

    def test_service_rejects_customer_ownership_mismatch(self):
        other_customer = User.objects.create_user(
            username='other-customer',
            email='other-customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
        )

        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-5',
                sale=self.sale,
                customer=other_customer,
                cashier=self.cashier,
                amount='10.00',
                payment_method='CASH',
            )

    def test_service_rejects_non_staff_cashier(self):
        non_staff = User.objects.create_user(
            username='plain-user',
            email='plain-user@example.com',
            password='StrongPass123',
            role='CUSTOMER',
        )

        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-6',
                sale=self.sale,
                customer=self.customer,
                cashier=non_staff,
                amount='10.00',
                payment_method='CASH',
            )

    def test_service_normalizes_transfer_method(self):
        payment = PaymentService.create_payment(
            payment_reference='PMT-SERVICE-TRANSFER',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount='250.00',
            payment_method='TRANSFER',
            payment_status='PENDING',
        )

        self.assertEqual(payment.payment_method, Payment.PaymentMethod.BANK_TRANSFER)

    def test_service_canonicalizes_bank_transfer_input(self):
        payment = PaymentService.create_payment(
            payment_reference='PMT-SERVICE-BANK-TRANSFER',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount='250.00',
            payment_method='BANK_TRANSFER',
            payment_status='PENDING',
        )

        self.assertEqual(payment.payment_method, Payment.PaymentMethod.BANK_TRANSFER)

    def test_service_preserves_transaction_integrity_on_validation_failure(self):
        before_count = Payment.objects.count()

        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-SERVICE-INVALID-7',
                sale=self.sale,
                order=self.order,
                customer=self.customer,
                cashier=self.cashier,
                amount='10.00',
                payment_method='CASH',
            )

        self.assertEqual(Payment.objects.count(), before_count)

    def test_service_returns_existing_payment_after_idempotency_race(self):
        existing = Payment.objects.create(
            payment_reference='PMT-RACE-EXISTING',
            idempotency_key='idemp-race-001',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('200.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        with patch.object(PaymentService, 'get_idempotent_payment', side_effect=[None, existing]):
            payment = PaymentService.create_payment(
                payment_reference='PMT-RACE-CANDIDATE',
                idempotency_key='idemp-race-001',
                sale=self.sale,
                customer=self.customer,
                cashier=self.cashier,
                amount='200.00',
                payment_method='CASH',
                payment_status='PENDING',
            )

        self.assertEqual(payment.pk, existing.pk)
        self.assertEqual(Payment.objects.filter(idempotency_key='idemp-race-001').count(), 1)


class PaymentAggregationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='aggregation-customer',
            email='aggregation-customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.cashier = User.objects.create_user(
            username='aggregation-cashier',
            email='aggregation-cashier@example.com',
            password='StrongPass123',
            role='CASHIER',
        )
        self.order = Order.objects.create(
            order_number='AGG-ORDER-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('10000.00'),
        )
        self.sale = Sale.objects.create(
            sale_number='AGG-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('10000.00'),
        )

    def create_payment(self, transaction, amount, status, reference):
        return Payment.objects.create(
            payment_reference=reference,
            order=transaction if isinstance(transaction, Order) else None,
            sale=transaction if isinstance(transaction, Sale) else None,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal(amount),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=status,
        )

    def test_no_payments_returns_zeroes_for_order(self):
        balance = PaymentService.get_transaction_balance(self.order)
        self.assertEqual(balance['transaction_total'], Decimal('10000.00'))
        self.assertEqual(balance['completed_amount'], Decimal('0.00'))
        self.assertEqual(balance['pending_amount'], Decimal('0.00'))
        self.assertEqual(balance['outstanding_amount'], Decimal('10000.00'))
        self.assertEqual(balance['overpaid_amount'], Decimal('0.00'))

    def test_completed_payments_calculate_underpayment_exact_payment_and_overpayment(self):
        self.create_payment(self.order, '4000.00', Payment.PaymentStatus.COMPLETED, 'AGG-ORDER-1')
        self.create_payment(self.order, '3000.00', Payment.PaymentStatus.COMPLETED, 'AGG-ORDER-2')
        balance = PaymentService.get_transaction_balance(self.order)
        self.assertEqual(balance['completed_amount'], Decimal('7000.00'))
        self.assertEqual(balance['outstanding_amount'], Decimal('3000.00'))
        self.assertEqual(balance['overpaid_amount'], Decimal('0.00'))

        exact_sale = Sale.objects.create(
            sale_number='AGG-SALE-EXACT',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('10000.00'),
        )
        self.create_payment(exact_sale, '10000.00', Payment.PaymentStatus.COMPLETED, 'AGG-SALE-EXACT-PAY')
        exact_balance = PaymentService.get_transaction_balance(exact_sale)
        self.assertEqual(exact_balance['outstanding_amount'], Decimal('0.00'))
        self.assertEqual(exact_balance['overpaid_amount'], Decimal('0.00'))

        self.create_payment(self.sale, '7000.00', Payment.PaymentStatus.COMPLETED, 'AGG-SALE-1')
        self.create_payment(self.sale, '5000.00', Payment.PaymentStatus.COMPLETED, 'AGG-SALE-2')
        overpaid_balance = PaymentService.get_transaction_balance(self.sale)
        self.assertEqual(overpaid_balance['completed_amount'], Decimal('12000.00'))
        self.assertEqual(overpaid_balance['outstanding_amount'], Decimal('0.00'))
        self.assertEqual(overpaid_balance['overpaid_amount'], Decimal('2000.00'))

    def test_non_completed_statuses_are_reported_but_excluded_from_collected_amount(self):
        self.create_payment(self.order, '1000.01', Payment.PaymentStatus.PENDING, 'AGG-PENDING')
        self.create_payment(self.order, '2000.02', Payment.PaymentStatus.FAILED, 'AGG-FAILED')
        self.create_payment(self.order, '3000.03', Payment.PaymentStatus.REFUNDED, 'AGG-REFUNDED')
        self.create_payment(self.order, '4000.04', Payment.PaymentStatus.COMPLETED, 'AGG-COMPLETED')

        balance = PaymentService.get_transaction_balance(self.order)
        self.assertEqual(balance['completed_amount'], Decimal('4000.04'))
        self.assertEqual(balance['pending_amount'], Decimal('1000.01'))
        self.assertEqual(balance['failed_amount'], Decimal('2000.02'))
        self.assertEqual(balance['refunded_amount'], Decimal('3000.03'))
        self.assertEqual(balance['outstanding_amount'], Decimal('5999.96'))

    def test_calculation_does_not_mutate_transaction_or_payments(self):
        self.create_payment(self.sale, '1234.56', Payment.PaymentStatus.COMPLETED, 'AGG-NO-MUTATION')
        original_total = self.sale.total
        original_status = self.sale.status
        balance = PaymentService.get_transaction_balance(self.sale)
        self.sale.refresh_from_db()
        self.assertEqual(balance['completed_amount'], Decimal('1234.56'))
        self.assertEqual(self.sale.total, original_total)
        self.assertEqual(self.sale.status, original_status)
        self.assertEqual(Payment.objects.get(payment_reference='AGG-NO-MUTATION').amount, Decimal('1234.56'))


@skipUnlessDBFeature('has_select_for_update')
class PaymentConfirmationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(
            username='concurrent-owner', email='concurrent-owner@example.com', password='StrongPass123', role='OWNER'
        )
        cashier = User.objects.create_user(
            username='concurrent-cashier', email='concurrent-cashier@example.com', password='StrongPass123', role='CASHIER'
        )
        category = ProductCategory.objects.create(name='Concurrent Payments', slug='concurrent-payments')
        product = Product.objects.create(
            name='Concurrent Payment Product', slug='concurrent-payment-product', sku='CONCURRENT-001',
            category=category, selling_price=Decimal('100.00'),
        )
        sale = Sale.objects.create(
            sale_number='CONCURRENT-SALE-001', cashier=cashier, payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('100.00'),
        )
        self.payment = Payment.objects.create(
            payment_reference='CONCURRENT-PAYMENT-001', idempotency_key='CONCURRENT-IDEMP-001', sale=sale,
            cashier=cashier, amount=Decimal('100.00'), payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.PENDING,
        )

    def test_concurrent_confirmation_is_safe_and_audited_once(self):
        barrier = Barrier(2)

        def confirm_payment():
            barrier.wait()
            return PaymentService.confirm_payment(self.payment.id, self.owner).payment_status

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: confirm_payment(), range(2)))

        self.assertEqual(statuses, [Payment.PaymentStatus.COMPLETED, Payment.PaymentStatus.COMPLETED])
        self.assertEqual(ActivityLog.objects.filter(action_type=ActivityLog.ActionType.PAYMENT).count(), 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.COMPLETED)


class PaymentOrderIntegrationTests(TestCase):
    """Focused Payment -> Order integration behavior without changing Order lifecycle rules."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='order-customer',
            email='order-customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
            first_name='Order',
            last_name='Customer',
        )
        self.other_customer = User.objects.create_user(
            username='other-order-customer',
            email='other-order-customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
            first_name='Other',
            last_name='Customer',
        )
        self.cashier = User.objects.create_user(
            username='order-cashier',
            email='order-cashier@example.com',
            password='StrongPass123',
            role='CASHIER',
            first_name='Order',
            last_name='Cashier',
        )
        self.owner = User.objects.create_user(
            username='order-owner',
            email='order-owner@example.com',
            password='StrongPass123',
            role='OWNER',
            first_name='Order',
            last_name='Owner',
        )
        self.order = Order.objects.create(
            order_number='PAY-ORD-INT-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.TRANSFER,
            total=Decimal('250.00'),
            subtotal=Decimal('250.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )

    def test_valid_order_payment_creates_payment_without_changing_order(self):
        payment = PaymentService.create_payment(
            payment_reference='PMT-ORDER-VALID',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount='250.00',
            payment_method='TRANSFER',
            payment_status='COMPLETED',
            transaction_reference='TXN-ORDER-VALID',
            allow_completed=True,
        )

        self.assertEqual(payment.order_id, self.order.id)
        self.assertEqual(payment.customer_id, self.customer.id)
        self.assertEqual(payment.amount, Decimal('250.00'))
        self.assertEqual(payment.payment_method, Payment.PaymentMethod.BANK_TRANSFER)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.order.total, Decimal('250.00'))

    def test_missing_order_and_nonexistent_order_are_rejected(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-ORDER-MISSING',
                order=None,
                customer=self.customer,
                cashier=self.cashier,
                amount='50.00',
                payment_method='CASH',
            )

        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-ORDER-NONEXISTENT',
                order=Order(id=999999),
                customer=self.customer,
                cashier=self.cashier,
                amount='50.00',
                payment_method='CASH',
            )

    def test_customer_mismatch_and_isolation_are_enforced_for_order_payment(self):
        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-ORDER-MISMATCH',
                order=self.order,
                customer=self.other_customer,
                cashier=self.cashier,
                amount='50.00',
                payment_method='CASH',
            )

        self.client.force_login(self.owner)
        payload = {
            'order_id': self.order.id,
            'customer_id': self.customer.id,
            'cashier_id': self.cashier.id,
            'amount': '50.00',
            'payment_method': 'CASH',
            'payment_status': 'PENDING',
        }
        response = self.client.post('/payments/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)

        self.client.force_login(self.other_customer)
        response = self.client.get('/payments/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']
        self.assertEqual(payload['pagination']['total_count'], 0)

    def test_order_payment_uses_service_and_rejects_duplicate_reference(self):
        payment = Payment.objects.create(
            payment_reference='PMT-ORDER-DUPLICATE',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('50.00'),
            payment_method=Payment.PaymentMethod.CASH,
        )

        with patch('apps.payments.views.PaymentService.create_payment', autospec=True) as mock_create:
            mock_create.return_value = payment
            self.client.force_login(self.owner)
            response = self.client.post(
                '/payments/',
                data=json.dumps({
                    'order_id': self.order.id,
                    'customer_id': self.customer.id,
                    'cashier_id': self.cashier.id,
                    'amount': '40.00',
                    'payment_method': 'CASH',
                    'payment_status': 'PENDING',
                    'transaction_reference': 'TXN-DUPLICATE',
                }),
                content_type='application/json',
            )
            self.assertTrue(mock_create.called)
            self.assertEqual(mock_create.call_args.kwargs['order'], self.order)
            self.assertEqual(response.status_code, 201)

        with self.assertRaises(ValidationError):
            PaymentService.create_payment(
                payment_reference='PMT-ORDER-DUPLICATE',
                order=self.order,
                customer=self.customer,
                cashier=self.cashier,
                amount='60.00',
                payment_method='CASH',
            )

    def test_order_payment_api_requires_authorization_and_rejects_unsupported_method(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            '/payments/',
            data=json.dumps({
                'order_id': self.order.id,
                'customer_id': self.customer.id,
                'amount': '50.00',
                'payment_method': 'CASH',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.post(
            '/payments/',
            data=json.dumps({
                'order_id': self.order.id,
                'customer_id': self.customer.id,
                'cashier_id': self.cashier.id,
                'amount': '50.00',
                'payment_method': 'NOT_REAL',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('payment_method', response.json()['errors'])


class PaymentReconciliationPhase2Tests(TestCase):
    """Test Payment Reconciliation Phase 2 management views and endpoints."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='phase2-owner', email='phase2-owner@example.com', password='StrongPass123', role='OWNER',
            first_name='Owner', last_name='User',
        )
        self.manager = User.objects.create_user(
            username='phase2-manager', email='phase2-manager@example.com', password='StrongPass123', role='MANAGER',
            first_name='Manager', last_name='User',
        )
        self.cashier = User.objects.create_user(
            username='phase2-cashier', email='phase2-cashier@example.com', password='StrongPass123', role='CASHIER',
            first_name='Cashier', last_name='User',
        )
        self.staff = User.objects.create_user(
            username='phase2-staff', email='phase2-staff@example.com', password='StrongPass123', role='STAFF',
            first_name='Staff', last_name='User',
        )
        self.customer = User.objects.create_user(
            username='phase2-customer', email='phase2-customer@example.com', password='StrongPass123', role='CUSTOMER',
            first_name='Customer', last_name='User',
        )

        self.category = ProductCategory.objects.create(name='Phase 2 Recon Category', slug='phase-2-recon')
        self.product = Product.objects.create(
            name='Phase 2 Recon Product', slug='phase-2-recon-product', sku='P2-RECON-001',
            category=self.category, selling_price=Decimal('100.00'), cost_price=Decimal('60.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=100)

        self.sale = Sale.objects.create(
            sale_number='P2-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            amount_received=Decimal('100.00'),
            change_amount=Decimal('0.00'),
            payment_status=Sale.PaymentStatus.PENDING,
            status=Sale.SaleStatus.DRAFT,
        )
        self.order = Order.objects.create(
            order_number='P2-ORD-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Order.PaymentStatus.PENDING,
            status=Order.OrderStatus.PENDING,
        )

    def test_reconcile_endpoints_require_authentication(self):
        sale_url = f'/payments/reconcile/sale/{self.sale.id}/'
        order_url = f'/payments/reconcile/order/{self.order.id}/'
        overview_url = '/payments/reconcile/overview/'

        for url in (sale_url, order_url, overview_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], 'Authentication required.')

    def test_role_based_access_control_denies_customer_cashier_staff(self):
        sale_url = f'/payments/reconcile/sale/{self.sale.id}/'
        order_url = f'/payments/reconcile/order/{self.order.id}/'
        overview_url = '/payments/reconcile/overview/'

        unauthorized_users = [self.customer, self.cashier, self.staff]
        for user in unauthorized_users:
            self.client.force_login(user)
            for url in (sale_url, order_url, overview_url):
                with self.subTest(role=user.role, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertFalse(response.json()['success'])
                    self.assertEqual(response.json()['message'], 'Only owners and managers can access reconciliation.')

    def test_role_based_access_control_permits_owner_and_manager(self):
        sale_url = f'/payments/reconcile/sale/{self.sale.id}/'
        order_url = f'/payments/reconcile/order/{self.order.id}/'
        overview_url = '/payments/reconcile/overview/'

        authorized_users = [self.owner, self.manager]
        for user in authorized_users:
            self.client.force_login(user)
            for url in (sale_url, order_url, overview_url):
                with self.subTest(role=user.role, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()['success'])

    def test_reconcile_methods_reject_non_get(self):
        sale_url = f'/payments/reconcile/sale/{self.sale.id}/'
        order_url = f'/payments/reconcile/order/{self.order.id}/'
        overview_url = '/payments/reconcile/overview/'

        self.client.force_login(self.owner)
        for url in (sale_url, order_url, overview_url):
            for method in ('post', 'put', 'patch', 'delete'):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 405)
                    self.assertFalse(response.json()['success'])
                    self.assertEqual(response.json()['message'], 'Only GET is allowed.')

    def test_reconciliation_payload_unpaid_scenario(self):
        self.client.force_login(self.owner)
        order = Order.objects.create(
            order_number='P2-UNPAID-ORD',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('120.00'),
            subtotal=Decimal('120.00'),
            payment_status=Order.PaymentStatus.PENDING,
            status=Order.OrderStatus.PENDING,
        )

        response = self.client.get(f'/payments/reconcile/order/{order.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()['data']
        self.assertEqual(data['classification'], 'UNPAID')
        self.assertEqual(data['transaction_type'], 'ORDER')
        self.assertEqual(data['transaction_id'], order.id)
        self.assertEqual(data['transaction_total'], '120.00')
        self.assertEqual(data['completed_amount'], '0.00')
        self.assertEqual(data['outstanding_amount'], '120.00')
        self.assertEqual(data['overpaid_amount'], '0.00')
        self.assertEqual(data['payment_count'], 0)

    def test_reconciliation_payload_partially_paid_scenario(self):
        self.client.force_login(self.manager)
        order = Order.objects.create(
            order_number='P2-PART-ORD',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )
        Payment.objects.create(
            payment_reference='P2-PMT-PART',
            order=order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('45.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        response = self.client.get(f'/payments/reconcile/order/{order.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()['data']
        self.assertEqual(data['classification'], 'PARTIALLY_PAID')
        self.assertEqual(data['completed_amount'], '45.00')
        self.assertEqual(data['outstanding_amount'], '55.00')
        self.assertEqual(data['overpaid_amount'], '0.00')
        self.assertEqual(data['payment_count'], 1)

    def test_reconciliation_payload_fully_paid_scenario(self):
        self.client.force_login(self.owner)
        sale = Sale.objects.create(
            sale_number='P2-FULL-SALE',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('200.00'),
            subtotal=Decimal('200.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='P2-PMT-FULL',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('200.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        response = self.client.get(f'/payments/reconcile/sale/{sale.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()['data']
        self.assertEqual(data['classification'], 'FULLY_PAID')
        self.assertEqual(data['completed_amount'], '200.00')
        self.assertEqual(data['outstanding_amount'], '0.00')
        self.assertEqual(data['overpaid_amount'], '0.00')
        self.assertEqual(data['completed_payment_count'], 1)

    def test_reconciliation_payload_overpaid_scenario(self):
        self.client.force_login(self.manager)
        sale = Sale.objects.create(
            sale_number='P2-OVER-SALE',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('100.00'),
            subtotal=Decimal('100.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        Payment.objects.create(
            payment_reference='P2-PMT-OVER',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('160.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        response = self.client.get(f'/payments/reconcile/sale/{sale.id}/')
        self.assertEqual(response.status_code, 200)

        data = response.json()['data']
        self.assertEqual(data['classification'], 'OVERPAID')
        self.assertEqual(data['completed_amount'], '160.00')
        self.assertEqual(data['outstanding_amount'], '0.00')
        self.assertEqual(data['overpaid_amount'], '60.00')
        self.assertIn('COMPLETED_PAYMENT_EXCEEDS_TRANSACTION_TOTAL', data['inconsistency_findings'])

    def test_bulk_reconciliation_overview_and_filtering(self):
        self.client.force_login(self.owner)
        response = self.client.get('/payments/reconcile/overview/')
        self.assertEqual(response.status_code, 200)

        data = response.json()['data']
        self.assertIn('summary', data)
        self.assertIn('transactions', data)
        self.assertGreaterEqual(data['summary']['total_transactions'], 2)
        self.assertIn('classifications', data['summary'])
        self.assertIn('inconsistency_count', data['summary'])

        # Filter by type=sale
        sale_resp = self.client.get('/payments/reconcile/overview/?type=sale')
        self.assertEqual(sale_resp.status_code, 200)
        for item in sale_resp.json()['data']['transactions']:
            self.assertEqual(item['transaction_type'], 'SALE')

        # Filter by type=order
        order_resp = self.client.get('/payments/reconcile/overview/?type=order')
        self.assertEqual(order_resp.status_code, 200)
        for item in order_resp.json()['data']['transactions']:
            self.assertEqual(item['transaction_type'], 'ORDER')

        # Limit
        limit_resp = self.client.get('/payments/reconcile/overview/?limit=1')
        self.assertEqual(limit_resp.status_code, 200)
        self.assertEqual(len(limit_resp.json()['data']['transactions']), 1)

    def test_audit_logging_integrated_on_reconciliation_reports(self):
        initial_log_count = ActivityLog.objects.count()

        # 1. View sale reconciliation
        self.client.force_login(self.owner)
        self.client.get(f'/payments/reconcile/sale/{self.sale.id}/')
        self.assertEqual(ActivityLog.objects.count(), initial_log_count + 1)
        latest_log = ActivityLog.objects.order_by('-created_at', '-id').first()
        self.assertEqual(latest_log.actor, self.owner)
        self.assertEqual(latest_log.action_type, ActivityLog.ActionType.VIEWED)
        self.assertEqual(latest_log.action_label, 'Viewed sale reconciliation')
        self.assertEqual(latest_log.related_object, self.sale)
        self.assertEqual(latest_log.metadata['sale_id'], self.sale.id)

        # 2. View order reconciliation
        self.client.force_login(self.manager)
        self.client.get(f'/payments/reconcile/order/{self.order.id}/')
        self.assertEqual(ActivityLog.objects.count(), initial_log_count + 2)
        latest_log = ActivityLog.objects.order_by('-created_at', '-id').first()
        self.assertEqual(latest_log.actor, self.manager)
        self.assertEqual(latest_log.action_type, ActivityLog.ActionType.VIEWED)
        self.assertEqual(latest_log.action_label, 'Viewed order reconciliation')
        self.assertEqual(latest_log.related_object, self.order)
        self.assertEqual(latest_log.metadata['order_id'], self.order.id)

        # 3. View overview
        self.client.force_login(self.owner)
        self.client.get('/payments/reconcile/overview/')
        self.assertEqual(ActivityLog.objects.count(), initial_log_count + 3)
        latest_log = ActivityLog.objects.order_by('-created_at', '-id').first()
        self.assertEqual(latest_log.actor, self.owner)
        self.assertEqual(latest_log.action_type, ActivityLog.ActionType.VIEWED)
        self.assertEqual(latest_log.action_label, 'Viewed reconciliation overview')

    def test_strict_read_only_database_state_remains_unchanged(self):
        from apps.credits.models import CreditAccount, CreditTransaction
        credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('5000.00'),
            outstanding_balance=Decimal('1000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
        )

        Payment.objects.create(
            payment_reference='P2-RO-PMT',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('50.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        # Snapshot before
        payment_snapshots = list(Payment.objects.values('id', 'payment_status', 'amount', 'payment_reference'))
        sale_snapshot = (
            self.sale.status, self.sale.payment_status, self.sale.total,
            self.sale.amount_received, self.sale.change_amount, self.sale.subtotal,
        )
        order_snapshot = (
            self.order.status, self.order.payment_status, self.order.total, self.order.subtotal,
        )
        inventory_snapshot = self.inventory.quantity
        credit_snapshot = (credit_account.outstanding_balance, credit_account.credit_limit, credit_account.status)
        credit_tx_count = CreditTransaction.objects.count()

        self.client.force_login(self.owner)
        self.client.get(f'/payments/reconcile/sale/{self.sale.id}/')
        self.client.get(f'/payments/reconcile/order/{self.order.id}/')
        self.client.get('/payments/reconcile/overview/')

        # Refresh and verify
        self.sale.refresh_from_db()
        self.order.refresh_from_db()
        self.inventory.refresh_from_db()
        credit_account.refresh_from_db()

        self.assertEqual(
            list(Payment.objects.values('id', 'payment_status', 'amount', 'payment_reference')),
            payment_snapshots,
        )
        self.assertEqual(
            (
                self.sale.status, self.sale.payment_status, self.sale.total,
                self.sale.amount_received, self.sale.change_amount, self.sale.subtotal,
            ),
            sale_snapshot,
        )
        self.assertEqual(
            (self.order.status, self.order.payment_status, self.order.total, self.order.subtotal),
            order_snapshot,
        )
        self.assertEqual(self.inventory.quantity, inventory_snapshot)
        self.assertEqual(
            (credit_account.outstanding_balance, credit_account.credit_limit, credit_account.status),
            credit_snapshot,
        )
        self.assertEqual(CreditTransaction.objects.count(), credit_tx_count)

    def test_not_found_and_uuid_handling(self):
        self.client.force_login(self.owner)

        nonexistent_uuid = str(uuid.uuid4())
        for entity, bad_ids in [
            ('sale', ['999999', nonexistent_uuid, 'invalid-str']),
            ('order', ['999999', nonexistent_uuid, 'invalid-str']),
        ]:
            for bad_id in bad_ids:
                with self.subTest(entity=entity, bad_id=bad_id):
                    response = self.client.get(f'/payments/reconcile/{entity}/{bad_id}/')
                    self.assertEqual(response.status_code, 404)
                    self.assertFalse(response.json()['success'])
                    self.assertEqual(response.json()['message'], f'{entity.capitalize()} not found.')


class DjangoSystemChecksTests(TestCase):
    """Test Django system checks pass for Payments app."""

    def test_payments_app_checks_pass(self):
        out = __import__('io').StringIO()
        call_command('check', stdout=out)
        output = out.getvalue()
        self.assertNotIn('error', output.lower())


class PaymentVerificationPhase3Tests(TestCase):
    """Comprehensive unit and integration tests for Payment Reconciliation Phase 3

    (Provider-Neutral Verification Layer).
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='phase3-owner', email='phase3-owner@example.com', password='StrongPass123', role='OWNER',
            first_name='Owner', last_name='User',
        )
        self.manager = User.objects.create_user(
            username='phase3-manager', email='phase3-manager@example.com', password='StrongPass123', role='MANAGER',
            first_name='Manager', last_name='User',
        )
        self.cashier = User.objects.create_user(
            username='phase3-cashier', email='phase3-cashier@example.com', password='StrongPass123', role='CASHIER',
            first_name='Cashier', last_name='User',
        )
        self.staff = User.objects.create_user(
            username='phase3-staff', email='phase3-staff@example.com', password='StrongPass123', role='STAFF',
            first_name='Staff', last_name='User',
        )
        self.customer = User.objects.create_user(
            username='phase3-customer', email='phase3-customer@example.com', password='StrongPass123', role='CUSTOMER',
            first_name='Customer', last_name='User',
        )

        self.category = ProductCategory.objects.create(name='Phase 3 Category', slug='phase-3-cat')
        self.product = Product.objects.create(
            name='Phase 3 Product', slug='phase-3-prod', sku='P3-SKU-001',
            category=self.category, selling_price=Decimal('500.00'), cost_price=Decimal('300.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=50)

        self.sale = Sale.objects.create(
            sale_number='P3-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('500.00'),
            subtotal=Decimal('500.00'),
            amount_received=Decimal('500.00'),
            change_amount=Decimal('0.00'),
            payment_status=Sale.PaymentStatus.COMPLETED,
            status=Sale.SaleStatus.COMPLETED,
        )
        self.order = Order.objects.create(
            order_number='P3-ORD-001',
            customer=self.customer,
            created_by=self.cashier,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('500.00'),
            subtotal=Decimal('500.00'),
            payment_status=Order.PaymentStatus.CONFIRMED,
            status=Order.OrderStatus.CONFIRMED,
        )

        self.payment_completed = Payment.objects.create(
            payment_reference='P3-PMT-COMPLETED',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-REF-101',
            transaction_metadata={'gateway': 'internal_test'},
        )
        self.payment_pending = Payment.objects.create(
            payment_reference='P3-PMT-PENDING',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
            transaction_reference='TXN-REF-102',
        )
        self.payment_failed = Payment.objects.create(
            payment_reference='P3-PMT-FAILED',
            order=self.order,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('200.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.FAILED,
            transaction_reference='TXN-REF-103',
        )
        self.payment_refunded = Payment.objects.create(
            payment_reference='P3-PMT-REFUNDED',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('100.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.REFUNDED,
            transaction_reference='TXN-REF-104',
        )

    # 1. Architecture & Service Layer Unit Tests
    def test_verification_result_structure_and_serialization(self):
        result = PaymentVerificationResult(
            status=PaymentVerificationStatus.VERIFIED.value,
            verified_amount=Decimal('500.00'),
            provider_reference='TXN-REF-101',
            payment_reference='P3-PMT-COMPLETED',
            payment_id=self.payment_completed.id,
            provider='mock',
            discrepancies=[],
            metadata={'test': True},
        )
        self.assertTrue(result.is_verified)
        self.assertFalse(result.has_discrepancy)
        data = result.to_dict()
        self.assertEqual(data['status'], 'VERIFIED')
        self.assertEqual(data['verified_amount'], '500.00')
        self.assertEqual(data['provider_reference'], 'TXN-REF-101')
        self.assertEqual(data['payment_reference'], 'P3-PMT-COMPLETED')
        self.assertEqual(data['payment_id'], self.payment_completed.id)
        self.assertEqual(data['provider'], 'mock')
        self.assertEqual(data['discrepancies'], [])
        self.assertFalse(data['discrepancy_detected'])
        self.assertIn('verification_timestamp', data)
        self.assertEqual(data['metadata'], {'test': True})

    def test_mock_verifier_completed_payment_returns_verified(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_completed)
        self.assertEqual(result.status, PaymentVerificationStatus.VERIFIED.value)
        self.assertTrue(result.is_verified)
        self.assertEqual(result.verified_amount, Decimal('500.00'))
        self.assertEqual(result.provider_reference, 'TXN-REF-101')
        self.assertEqual(result.discrepancies, [])
        self.assertFalse(result.has_discrepancy)

    def test_mock_verifier_pending_payment_returns_pending(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_pending)
        self.assertEqual(result.status, PaymentVerificationStatus.PENDING.value)
        self.assertFalse(result.is_verified)
        self.assertEqual(result.verified_amount, Decimal('500.00'))

    def test_mock_verifier_failed_payment_returns_failed(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_failed)
        self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
        self.assertFalse(result.is_verified)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(len(result.discrepancies) > 0)

    def test_mock_verifier_refunded_payment_returns_mismatch(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_refunded)
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)

    def test_mock_verifier_detects_amount_mismatch_metadata(self):
        payment = Payment.objects.create(
            payment_reference='P3-PMT-AMT-DIFF',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-REF-AMT',
            transaction_metadata={'mock_verified_amount': '450.00'},
        )
        verifier = MockPaymentVerifier()
        result = verifier.verify(payment)
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(any('Amount mismatch' in d for d in result.discrepancies))

    def test_mock_verifier_detects_amount_mismatch_kwargs(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_completed, expected_amount=Decimal('999.00'))
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(any('Amount mismatch' in d for d in result.discrepancies))

    def test_mock_verifier_detects_reference_mismatch_metadata(self):
        payment = Payment.objects.create(
            payment_reference='P3-PMT-REF-DIFF',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-RECORDED',
            transaction_metadata={'mock_reference': 'TXN-EXTERNAL-OTHER'},
        )
        verifier = MockPaymentVerifier()
        result = verifier.verify(payment)
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(any('Reference mismatch' in d for d in result.discrepancies))

    def test_mock_verifier_detects_reference_mismatch_kwargs(self):
        verifier = MockPaymentVerifier()
        result = verifier.verify(self.payment_completed, expected_reference='WRONG-REF')
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(any('Reference mismatch' in d for d in result.discrepancies))

    def test_mock_verifier_detects_currency_mismatch(self):
        payment = Payment.objects.create(
            payment_reference='P3-PMT-CURR-DIFF',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_metadata={'currency': 'USD'},
        )
        verifier = MockPaymentVerifier()
        result = verifier.verify(payment)
        self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
        self.assertTrue(result.has_discrepancy)
        self.assertTrue(any('Currency mismatch' in d for d in result.discrepancies))

    def test_mock_verifier_simulated_mock_status_flag(self):
        payment = Payment.objects.create(
            payment_reference='P3-PMT-SIM-STATUS',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('500.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_metadata={'mock_status': 'FAILED'},
        )
        verifier = MockPaymentVerifier()
        result = verifier.verify(payment)
        self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)

    def test_mock_verifier_requires_saved_payment_instance(self):
        verifier = MockPaymentVerifier()
        with self.assertRaises(ValidationError):
            verifier.verify(None)
        unsaved_payment = Payment(payment_reference='UNSAVED')
        with self.assertRaises(ValidationError):
            verifier.verify(unsaved_payment)

    def test_internal_verifier_subclass(self):
        verifier = InternalPaymentVerifier()
        result = verifier.verify(self.payment_completed)
        self.assertEqual(result.provider, 'internal')
        self.assertEqual(result.status, PaymentVerificationStatus.VERIFIED.value)

    def test_service_verifier_registration_and_extensibility(self):
        class DummyCustomVerifier(BasePaymentVerifier):
            provider_name = 'custom_gateway'
            def verify(self, payment, **kwargs):
                return PaymentVerificationResult(
                    status=PaymentVerificationStatus.VERIFIED.value,
                    verified_amount=payment.amount,
                    provider=self.provider_name,
                )

        PaymentVerificationService.register_verifier('custom_gateway', DummyCustomVerifier)
        verifier = PaymentVerificationService.get_verifier('custom_gateway')
        self.assertIsInstance(verifier, DummyCustomVerifier)
        result = PaymentVerificationService.verify_payment_transaction(self.payment_completed, provider='custom_gateway')
        self.assertEqual(result.provider, 'custom_gateway')

        # Invalid registration rejected
        with self.assertRaises(TypeError):
            PaymentVerificationService.register_verifier('invalid', str)

    def test_service_and_payment_service_convenience_methods(self):
        res1 = verify_payment_transaction(self.payment_completed)
        self.assertEqual(res1.status, PaymentVerificationStatus.VERIFIED.value)

        res2 = PaymentService.verify_payment(self.payment_completed)
        self.assertEqual(res2.status, PaymentVerificationStatus.VERIFIED.value)

    # 2. Endpoint & Access Control Integration Tests (POST /payments/<id>/verify/)
    def test_endpoint_unauthenticated_returns_401(self):
        response = self.client.post(f'/payments/{self.payment_completed.id}/verify/')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])
        self.assertEqual(response.json()['message'], 'Authentication required.')

    def test_endpoint_role_access_control(self):
        url = f'/payments/{self.payment_completed.id}/verify/'

        # Unauthorized roles
        for user in [self.customer, self.cashier, self.staff]:
            self.client.force_login(user)
            with self.subTest(role=user.role):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], 'Only owners and managers can verify payments.')

        # Authorized roles
        for user in [self.owner, self.manager]:
            self.client.force_login(user)
            with self.subTest(role=user.role):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()['success'])

    def test_endpoint_method_not_allowed_on_non_post(self):
        self.client.force_login(self.owner)
        url = f'/payments/{self.payment_completed.id}/verify/'
        for method in ['get', 'put', 'patch', 'delete']:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], 'Only POST is allowed.')

    def test_endpoint_success_by_integer_id(self):
        self.client.force_login(self.owner)
        response = self.client.post(f'/payments/{self.payment_completed.id}/verify/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['payment_id'], self.payment_completed.id)
        self.assertEqual(data['payment_reference'], 'P3-PMT-COMPLETED')
        self.assertEqual(data['provider_reference'], 'TXN-REF-101')
        self.assertEqual(data['verified_amount'], '500.00')
        self.assertEqual(data['status'], 'VERIFIED')
        self.assertEqual(data['discrepancies'], [])
        self.assertFalse(data['discrepancy_detected'])
        self.assertIn('verification_timestamp', data)

    def test_endpoint_success_by_payment_reference_str(self):
        self.client.force_login(self.manager)
        response = self.client.post(f'/payments/{self.payment_completed.payment_reference}/verify/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['payment_id'], self.payment_completed.id)
        self.assertEqual(data['status'], 'VERIFIED')

    def test_endpoint_success_by_transaction_reference_str(self):
        self.client.force_login(self.manager)
        response = self.client.post(f'/payments/{self.payment_completed.transaction_reference}/verify/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['payment_id'], self.payment_completed.id)
        self.assertEqual(data['status'], 'VERIFIED')

    def test_endpoint_not_found_404(self):
        self.client.force_login(self.owner)
        for bad_id in ['999999', str(uuid.uuid4()), 'NONEXISTENT-REF']:
            with self.subTest(bad_id=bad_id):
                response = self.client.post(f'/payments/{bad_id}/verify/')
                self.assertEqual(response.status_code, 404)
                self.assertFalse(response.json()['success'])
                self.assertEqual(response.json()['message'], 'Payment not found.')

    def test_endpoint_detects_amount_and_reference_mismatches(self):
        self.client.force_login(self.owner)
        url = f'/payments/{self.payment_completed.id}/verify/'

        # Payload with different expected amount
        response = self.client.post(
            url,
            data=json.dumps({'expected_amount': '999.00'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['status'], 'MISMATCH')
        self.assertTrue(data['discrepancy_detected'])
        self.assertTrue(any('Amount mismatch' in d for d in data['discrepancies']))

        # Payload with different expected reference
        response = self.client.post(
            url,
            data=json.dumps({'expected_reference': 'UNEXPECTED-REF'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['status'], 'MISMATCH')
        self.assertTrue(data['discrepancy_detected'])
        self.assertTrue(any('Reference mismatch' in d for d in data['discrepancies']))

    def test_endpoint_creates_activity_log_audit_entry(self):
        self.client.force_login(self.owner)
        initial_log_count = ActivityLog.objects.count()

        response = self.client.post(f'/payments/{self.payment_completed.id}/verify/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ActivityLog.objects.count(), initial_log_count + 1)

        latest_log = ActivityLog.objects.order_by('-created_at', '-id').first()
        self.assertEqual(latest_log.actor, self.owner)
        self.assertEqual(latest_log.action_type, ActivityLog.ActionType.VIEWED)
        self.assertEqual(latest_log.action_label, 'Verified payment transaction')
        self.assertEqual(latest_log.related_object, self.payment_completed)
        self.assertEqual(latest_log.metadata['payment_id'], self.payment_completed.id)
        self.assertEqual(latest_log.metadata['payment_reference'], self.payment_completed.payment_reference)
        self.assertEqual(latest_log.metadata['verification_status'], 'VERIFIED')

    def test_strict_read_only_database_state_preservation(self):
        from apps.credits.models import CreditAccount, CreditTransaction
        credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('5000.00'),
            outstanding_balance=Decimal('1000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
        )

        payment_snapshots = list(Payment.objects.values('id', 'payment_status', 'amount', 'payment_reference'))
        sale_snapshot = (
            self.sale.status, self.sale.payment_status, self.sale.total,
            self.sale.amount_received, self.sale.change_amount, self.sale.subtotal,
        )
        order_snapshot = (
            self.order.status, self.order.payment_status, self.order.total, self.order.subtotal,
        )
        inventory_snapshot = self.inventory.quantity
        credit_snapshot = (credit_account.outstanding_balance, credit_account.credit_limit, credit_account.status)
        credit_tx_count = CreditTransaction.objects.count()

        # Run verification via API
        self.client.force_login(self.owner)
        self.client.post(f'/payments/{self.payment_completed.id}/verify/')
        self.client.post(f'/payments/{self.payment_pending.id}/verify/')
        self.client.post(f'/payments/{self.payment_failed.id}/verify/')
        self.client.post(f'/payments/{self.payment_refunded.id}/verify/')

        # Refresh and assert zero mutations
        self.sale.refresh_from_db()
        self.order.refresh_from_db()
        self.inventory.refresh_from_db()
        credit_account.refresh_from_db()

        self.assertEqual(
            list(Payment.objects.values('id', 'payment_status', 'amount', 'payment_reference')),
            payment_snapshots,
        )
        self.assertEqual(
            (
                self.sale.status, self.sale.payment_status, self.sale.total,
                self.sale.amount_received, self.sale.change_amount, self.sale.subtotal,
            ),
            sale_snapshot,
        )
        self.assertEqual(
            (self.order.status, self.order.payment_status, self.order.total, self.order.subtotal),
            order_snapshot,
        )
        self.assertEqual(self.inventory.quantity, inventory_snapshot)
        self.assertEqual(
            (credit_account.outstanding_balance, credit_account.credit_limit, credit_account.status),
            credit_snapshot,
        )
        self.assertEqual(CreditTransaction.objects.count(), credit_tx_count)


class PaystackPaymentVerificationTests(TestCase):
    """
    Automated unit and integration tests for Payment Reconciliation Phase 4A:
    - Official Paystack adapter (PaystackPaymentVerifier)
    - Amount conversion (kobo to Naira)
    - Status mapping ('success', 'failed', 'abandoned', 'pending')
    - Amount & reference mismatch detection
    - Network timeout, 404, 401, 500 error handling
    - Missing secret key handling
    - Management API endpoint integration (/payments/<id>/verify/ with provider='paystack')
    - Moniepoint POS scaffolding verifier (MoniepointPaymentVerifier)
    - Strict read-only invariance
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='paystack_owner',
            email='paystack_owner@example.com',
            password='StrongPass123',
            role='OWNER',
        )
        self.customer = User.objects.create_user(
            username='paystack_customer',
            email='paystack_customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.order = Order.objects.create(
            customer=self.customer,
            order_number='ORD-PSTK-001',
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            subtotal=Decimal('10000.00'),
            total=Decimal('10000.00'),
        )
        self.payment = Payment.objects.create(
            payment_reference='PAY-PSTK-001',
            transaction_reference='PSTK-TX-10001',
            order=self.order,
            customer=self.customer,
            amount=Decimal('10000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

    def _make_mock_response(self, data_dict, code=200):
        class MockUrllibResponse:
            def __init__(self, body_bytes, status_code):
                self.body_bytes = body_bytes
                self.code = status_code

            def getcode(self):
                return self.code

            def read(self):
                return self.body_bytes

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        return MockUrllibResponse(json.dumps(data_dict).encode('utf-8'), code)

    def test_provider_registration(self):
        """Verify paystack and moniepoint are registered in PaymentVerificationService."""
        verifier_paystack = PaymentVerificationService.get_verifier('paystack')
        self.assertIsInstance(verifier_paystack, PaystackPaymentVerifier)
        self.assertEqual(verifier_paystack.provider_name, 'paystack')

        verifier_moniepoint = PaymentVerificationService.get_verifier('moniepoint')
        self.assertIsInstance(verifier_moniepoint, MoniepointPaymentVerifier)
        self.assertEqual(verifier_moniepoint.provider_name, 'moniepoint')

    def test_missing_secret_key_returns_unknown_status(self):
        """Verifier returns UNKNOWN status when PAYSTACK_SECRET_KEY is absent."""
        verifier = PaystackPaymentVerifier(secret_key='')
        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': ''}, clear=False):
            with patch('django.conf.settings.PAYSTACK_SECRET_KEY', ''):
                result = verifier.verify(self.payment, secret_key='')
                self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
                self.assertFalse(result.is_verified)
                self.assertTrue(result.has_discrepancy)
                self.assertTrue(any('PAYSTACK_SECRET_KEY' in d for d in result.discrepancies))

    def test_missing_reference_returns_failed_status(self):
        """Verifier returns FAILED when payment has no references."""
        verifier = PaystackPaymentVerifier(secret_key='sk_test_fake')
        result = verifier.verify(self.payment, reference='')
        self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
        self.assertTrue(any('No payment or transaction reference' in d for d in result.discrepancies))

    def test_verified_transaction_matching_recorded_amount(self):
        """Paystack success with matching amount (N10,000 = 1,000,000 kobo) returns VERIFIED."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 1234567,
                'status': 'success',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,  # 10,000.00 Naira
                'currency': 'NGN',
                'channel': 'card',
                'gateway_response': 'Successful',
                'paid_at': '2026-10-13T06:00:00.000Z',
                'fees': 15000,
                'customer': {'email': 'paystack_customer@example.com'},
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.VERIFIED.value)
            self.assertTrue(result.is_verified)
            self.assertFalse(result.has_discrepancy)
            self.assertEqual(result.verified_amount, Decimal('10000.00'))
            self.assertEqual(result.provider_reference, 'PSTK-TX-10001')
            self.assertEqual(result.metadata['channel'], 'card')
            self.assertEqual(result.metadata['fees_naira'], '150.00')

    def test_amount_mismatch_detection(self):
        """Recorded N10,000 vs. Paystack verified N5,000 (500,000 kobo) returns MISMATCH."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 1234568,
                'status': 'success',
                'reference': 'PSTK-TX-10001',
                'amount': 500000,  # 5,000.00 Naira (recorded is 10,000.00)
                'currency': 'NGN',
                'channel': 'bank_transfer',
                'gateway_response': 'Successful',
                'paid_at': '2026-10-13T06:05:00.000Z',
                'customer': {'email': 'paystack_customer@example.com'},
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertFalse(result.is_verified)
            self.assertTrue(result.has_discrepancy)
            self.assertEqual(result.verified_amount, Decimal('5000.00'))
            self.assertTrue(any('Amount mismatch' in d for d in result.discrepancies))

    def test_failed_provider_response(self):
        """Paystack transaction with 'failed' status returns FAILED."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 1234569,
                'status': 'failed',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'NGN',
                'gateway_response': 'Declined: Insufficient Funds',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertFalse(result.is_verified)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('Insufficient Funds' in d for d in result.discrepancies))

    def test_abandoned_provider_response(self):
        """Paystack transaction with 'abandoned' status returns FAILED."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 1234570,
                'status': 'abandoned',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'NGN',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertTrue(any('abandoned' in d for d in result.discrepancies))

    def test_pending_provider_response(self):
        """Paystack transaction with 'pending' status returns PENDING."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 1234571,
                'status': 'pending',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'NGN',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.PENDING.value)

    def test_network_timeout_handling(self):
        """Network timeout returns UNKNOWN status gracefully without crashing."""
        import socket
        with patch('urllib.request.urlopen', side_effect=socket.timeout('Connection timed out')):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('timeout' in d.lower() for d in result.discrepancies))

    def test_http_404_reference_not_found(self):
        """HTTP 404 from Paystack returns FAILED status with clear message."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.paystack.co/transaction/verify/PSTK-TX-10001',
            code=404,
            msg='Not Found',
            hdrs={},
            fp=io.BytesIO(b'{"status":false,"message":"Transaction reference not found"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertTrue(any('404' in d for d in result.discrepancies))

    def test_http_401_authentication_failure(self):
        """HTTP 401/403 from Paystack returns UNKNOWN status advising key check."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.paystack.co/transaction/verify/PSTK-TX-10001',
            code=401,
            msg='Unauthorized',
            hdrs={},
            fp=io.BytesIO(b'{"status":false,"message":"Invalid key"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(any('PAYSTACK_SECRET_KEY' in d for d in result.discrepancies))

    def test_http_500_api_error_handling(self):
        """HTTP 500 from Paystack returns UNKNOWN status."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.paystack.co/transaction/verify/PSTK-TX-10001',
            code=500,
            msg='Internal Server Error',
            hdrs={},
            fp=io.BytesIO(b'{"status":false,"message":"Server error"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(any('500' in d for d in result.discrepancies))

    def test_currency_mismatch_detection(self):
        """Paystack transaction in non-NGN currency (e.g. USD) returns MISMATCH."""
        paystack_payload = {
            'status': True,
            'data': {
                'id': 1234572,
                'status': 'success',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'USD',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertTrue(any('Currency mismatch' in d for d in result.discrepancies))

    def test_management_api_endpoint_with_paystack_provider(self):
        """POST /payments/<id>/verify/ with provider='paystack' delegates to Paystack verifier."""
        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 998877,
                'status': 'success',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'NGN',
                'channel': 'card',
                'gateway_response': 'Approved',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        self.client.force_login(self.owner)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            url = f'/payments/{self.payment.id}/verify/'
            response = self.client.post(
                url,
                data=json.dumps({'provider': 'paystack', 'secret_key': 'sk_test_endpoint'}),
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()['data']
            self.assertEqual(data['status'], 'VERIFIED')
            self.assertEqual(data['provider'], 'paystack')
            self.assertEqual(data['verified_amount'], '10000.00')

    def test_paystack_read_only_invariance(self):
        """Paystack verification is strictly read-only and never alters database state."""
        paystack_payload = {
            'status': True,
            'data': {
                'id': 1234573,
                'status': 'success',
                'reference': 'PSTK-TX-10001',
                'amount': 1000000,
                'currency': 'NGN',
            },
        }

        mock_resp = self._make_mock_response(paystack_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = PaystackPaymentVerifier(secret_key='sk_test_fake')
            verifier.verify(self.payment)

            self.payment.refresh_from_db()
            self.order.refresh_from_db()

            self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.PENDING)
            self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
            self.assertEqual(self.payment.amount, Decimal('10000.00'))


class MoniepointPaymentVerificationTests(TestCase):
    """
    Comprehensive tests for MoniepointPaymentVerifier (Phase 4B).
    Tests POS terminal querying, attribute matching, discrepancy detection,
    status mapping, timeout/error handling, and read-only preservation.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='monie_owner',
            email='monie_owner@example.com',
            password='StrongPass123',
            role='OWNER',
        )
        self.customer = User.objects.create_user(
            username='monie_customer',
            email='monie_customer@example.com',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.order = Order.objects.create(
            customer=self.customer,
            order_number='ORD-MNP-001',
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            subtotal=Decimal('12000.00'),
            total=Decimal('12000.00'),
        )
        self.payment = Payment.objects.create(
            payment_reference='PAY-MNP-001',
            transaction_reference='MNP-TX-99001',
            order=self.order,
            customer=self.customer,
            amount=Decimal('12000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
            transaction_metadata={
                'terminal_serial': 'MP_TERM_12345',
                'rrn': '000987654321',
            },
        )

    def _make_mock_response(self, data_dict, code=200):
        class MockUrllibResponse:
            def __init__(self, body_bytes, status_code):
                self.body_bytes = body_bytes
                self.code = status_code

            def getcode(self):
                return self.code

            def read(self):
                return self.body_bytes

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        return MockUrllibResponse(json.dumps(data_dict).encode('utf-8'), code)

    def test_provider_registration(self):
        """Verify moniepoint is registered in PaymentVerificationService."""
        verifier = PaymentVerificationService.get_verifier('moniepoint')
        self.assertIsInstance(verifier, MoniepointPaymentVerifier)
        self.assertEqual(verifier.provider_name, 'moniepoint')

    def test_missing_api_key_returns_unknown_status(self):
        """Verifier returns UNKNOWN status when MONIEPOINT_API_KEY is absent."""
        verifier = MoniepointPaymentVerifier(api_key='')
        with patch.dict(os.environ, {'MONIEPOINT_API_KEY': ''}, clear=False):
            with patch('django.conf.settings.MONIEPOINT_API_KEY', ''):
                result = verifier.verify(self.payment, api_key='')
                self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
                self.assertFalse(result.is_verified)
                self.assertTrue(result.has_discrepancy)
                self.assertTrue(any('MONIEPOINT_API_KEY' in d for d in result.discrepancies))

    def test_missing_reference_returns_failed_status(self):
        """Verifier returns FAILED when payment has no references."""
        verifier = MoniepointPaymentVerifier(api_key='mp_api_fake123')
        result = verifier.verify(self.payment, reference='', merchant_reference='')
        self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
        self.assertTrue(any('No merchant reference or transaction reference' in d for d in result.discrepancies))

    def test_verified_moniepoint_pos_transaction_matching(self):
        """Moniepoint POS transaction matching amount, RRN, and terminal returns VERIFIED."""
        monie_payload = {
            'responseCode': '00',
            'responseMessage': 'Success',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'merchantReference': 'PAY-MNP-001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
                'paymentMethod': 'CARD',
                'transactionTime': '2026-10-13T12:00:00Z',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.VERIFIED.value)
            self.assertTrue(result.is_verified)
            self.assertFalse(result.has_discrepancy)
            self.assertEqual(result.verified_amount, Decimal('12000.00'))
            self.assertEqual(result.provider_reference, 'MNP-TX-99001')
            self.assertEqual(result.metadata['terminal_serial'], 'MP_TERM_12345')
            self.assertEqual(result.metadata['rrn'], '000987654321')
            self.assertEqual(result.metadata['processing_status'], 'SUCCESSFUL')

    def test_approved_status_maps_to_verified(self):
        """Moniepoint 'APPROVED' status maps to VERIFIED."""
        monie_payload = {
            'status': True,
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': 12000,
                'currency': 'NGN',
                'processingStatus': 'APPROVED',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.VERIFIED.value)
            self.assertTrue(result.is_verified)

    def test_amount_mismatch_detection(self):
        """Recorded N12,000 vs. terminal swiped N10,000 returns MISMATCH."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '10000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertFalse(result.is_verified)
            self.assertTrue(result.has_discrepancy)
            self.assertEqual(result.verified_amount, Decimal('10000.00'))
            self.assertTrue(any('Amount mismatch' in d for d in result.discrepancies))

    def test_terminal_serial_mismatch_detection(self):
        """Different terminal serial returns MISMATCH with clear discrepancy message."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'OTHER_POS_99999',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('Terminal serial mismatch' in d for d in result.discrepancies))

    def test_rrn_mismatch_detection(self):
        """Different RRN returns MISMATCH with clear discrepancy message."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': 'DIFFERENT_RRN_888',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('RRN mismatch' in d for d in result.discrepancies))

    def test_declined_terminal_transaction_response(self):
        """Moniepoint transaction with 'DECLINED' status returns FAILED."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'DECLINED',
                'message': 'PIN Incorrect / Insufficient Funds',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertFalse(result.is_verified)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('declined' in d.lower() for d in result.discrepancies))

    def test_failed_terminal_transaction_response(self):
        """Moniepoint transaction with 'FAILED' status returns FAILED."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'FAILED',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertTrue(any('failed' in d.lower() for d in result.discrepancies))

    def test_pending_terminal_transaction_response(self):
        """Moniepoint transaction with 'PENDING' status returns PENDING."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'PENDING',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.PENDING.value)

    def test_network_timeout_handling(self):
        """Network timeout returns UNKNOWN status gracefully without raising exception."""
        import socket
        with patch('urllib.request.urlopen', side_effect=socket.timeout('POS connection timed out')):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(result.has_discrepancy)
            self.assertTrue(any('timeout' in d.lower() for d in result.discrepancies))

    def test_http_404_reference_not_found(self):
        """HTTP 404 from Moniepoint returns FAILED status with clear message."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.pos.moniepoint.com/v1/transactions/merchants/MNP-TX-99001',
            code=404,
            msg='Not Found',
            hdrs={},
            fp=io.BytesIO(b'{"responseCode":"99","responseMessage":"Transaction reference not found"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.FAILED.value)
            self.assertTrue(any('404' in d for d in result.discrepancies))

    def test_http_401_authentication_failure(self):
        """HTTP 401 from Moniepoint returns UNKNOWN status advising key check."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.pos.moniepoint.com/v1/transactions/merchants/MNP-TX-99001',
            code=401,
            msg='Unauthorized',
            hdrs={},
            fp=io.BytesIO(b'{"responseCode":"01","responseMessage":"Invalid API key"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(any('MONIEPOINT_API_KEY' in d for d in result.discrepancies))

    def test_http_500_api_error_handling(self):
        """HTTP 500 from Moniepoint returns UNKNOWN status."""
        import io
        import urllib.error
        error = urllib.error.HTTPError(
            url='https://api.pos.moniepoint.com/v1/transactions/merchants/MNP-TX-99001',
            code=500,
            msg='Internal Server Error',
            hdrs={},
            fp=io.BytesIO(b'{"responseCode":"96","responseMessage":"System malfunction"}'),
        )

        with patch('urllib.request.urlopen', side_effect=error):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.UNKNOWN.value)
            self.assertTrue(any('500' in d for d in result.discrepancies))

    def test_currency_mismatch_detection(self):
        """Moniepoint transaction in non-NGN currency (e.g. USD) returns MISMATCH."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'USD',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_123')
            result = verifier.verify(self.payment)

            self.assertEqual(result.status, PaymentVerificationStatus.MISMATCH.value)
            self.assertTrue(any('Currency mismatch' in d for d in result.discrepancies))

    def test_management_api_endpoint_with_query_param_provider(self):
        """POST /payments/<id>/verify/?provider=moniepoint delegates to Moniepoint verifier."""
        monie_payload = {
            'responseCode': '00',
            'responseMessage': 'Success',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        self.client.force_login(self.owner)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            url = f'/payments/{self.payment.id}/verify/?provider=moniepoint'
            response = self.client.post(
                url,
                data=json.dumps({'api_key': 'mp_test_endpoint'}),
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()['data']
            self.assertEqual(data['status'], 'VERIFIED')
            self.assertEqual(data['provider'], 'moniepoint')
            self.assertEqual(data['verified_amount'], '12000.00')

    def test_management_api_endpoint_with_body_provider(self):
        """POST /payments/<id>/verify/ with provider in body delegates to Moniepoint."""
        monie_payload = {
            'responseCode': '00',
            'responseMessage': 'Success',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        self.client.force_login(self.owner)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            url = f'/payments/{self.payment.id}/verify/'
            response = self.client.post(
                url,
                data=json.dumps({'provider': 'moniepoint', 'api_key': 'mp_test_endpoint'}),
                content_type='application/json',
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()['data']
            self.assertEqual(data['status'], 'VERIFIED')
            self.assertEqual(data['provider'], 'moniepoint')

    def test_moniepoint_read_only_invariance(self):
        """Moniepoint verification is strictly read-only and never alters database state."""
        monie_payload = {
            'responseCode': '00',
            'data': {
                'terminalSerial': 'MP_TERM_12345',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TX-99001',
                'actualAmount': '12000.00',
                'currency': 'NGN',
                'processingStatus': 'SUCCESSFUL',
            },
        }

        mock_resp = self._make_mock_response(monie_payload)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            verifier = MoniepointPaymentVerifier(api_key='mp_test_read_only')
            verifier.verify(self.payment)

            self.payment.refresh_from_db()
            self.order.refresh_from_db()

            self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.PENDING)
            self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
            self.assertEqual(self.payment.amount, Decimal('12000.00'))


class QRCodePaymentTests(TestCase):
    """
    Comprehensive tests for Phase 4C: In-Store Dynamic Counter QR Payment Generation & Verification.
    Tests in-memory SVG/Data-URI generation, Paystack/Moniepoint standardized payloads,
    idempotent initialization, polling endpoints, and strict RBAC enforcement.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='qr_owner', email='qr_owner@example.com', password='StrongPass123', role='OWNER'
        )
        self.manager = User.objects.create_user(
            username='qr_manager', email='qr_manager@example.com', password='StrongPass123', role='MANAGER'
        )
        self.cashier = User.objects.create_user(
            username='qr_cashier', email='qr_cashier@example.com', password='StrongPass123', role='CASHIER'
        )
        self.customer = User.objects.create_user(
            username='qr_customer', email='qr_customer@example.com', password='StrongPass123', role='CUSTOMER'
        )
        self.other_customer = User.objects.create_user(
            username='qr_other_cust', email='qr_other@example.com', password='StrongPass123', role='CUSTOMER'
        )

        self.sale = Sale.objects.create(
            sale_number='MH-SALE-QR-001',
            cashier=self.cashier,
            customer=self.customer,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
            payment_method=Sale.PaymentMethod.TRANSFER,
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.PENDING,
        )

        self.order = Order.objects.create(
            order_number='ORD-QR-001',
            customer=self.customer,
            subtotal=Decimal('8500.00'),
            total=Decimal('8500.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )

    def test_in_memory_qr_generation_svg_and_data_uri(self):
        """Pure in-memory QR generates valid SVG and base64 data-uri with zero files on disk."""
        from apps.payments.qr_service import generate_qr_svg, generate_qr_data_uri

        test_payload = 'https://checkout.paystack.com/QR-TEST-001?amount=1500000&currency=NGN'
        svg = generate_qr_svg(test_payload)
        data_uri = generate_qr_data_uri(test_payload)

        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', svg)
        self.assertIn('viewBox=', svg)
        self.assertIn('</svg>', svg)

        import base64
        self.assertTrue(data_uri.startswith('data:image/svg+xml;base64,'))
        b64_content = data_uri.replace('data:image/svg+xml;base64,', '')
        decoded = base64.b64decode(b64_content).decode('utf-8')
        self.assertIn('<svg', decoded)

    def test_paystack_qr_payload_format_and_kobo_amount(self):
        """Paystack QR payload properly formats checkout URL and converts Naira to kobo."""
        from apps.payments.qr_service import build_paystack_qr_payload

        payload = build_paystack_qr_payload('TXN-QR-PSTK-001', Decimal('15000.00'))
        self.assertEqual(payload['provider'], 'paystack')
        self.assertEqual(payload['amount'], '15000.00')
        self.assertEqual(payload['kobo_amount'], 1500000)
        self.assertIn('checkout.paystack.com', payload['checkout_url'])
        self.assertIn('amount=1500000', payload['checkout_url'])

    def test_moniepoint_qr_payload_format(self):
        """Moniepoint QR payload properly formats transfer uri with exact amount and account details."""
        from apps.payments.qr_service import build_moniepoint_qr_payload

        payload = build_moniepoint_qr_payload('TXN-QR-MNP-001', Decimal('12500.50'), account_number='8099887766')
        self.assertEqual(payload['provider'], 'moniepoint')
        self.assertEqual(payload['amount'], '12500.50')
        self.assertIn('moniepoint://pay', payload['transfer_uri'])
        self.assertIn('amount=12500.50', payload['transfer_uri'])
        self.assertIn('accountNumber=8099887766', payload['transfer_uri'])

    def test_cashier_generates_qr_for_pos_sale(self):
        """Cashier successfully generates dynamic QR code for counter sale via API."""
        self.client.force_login(self.cashier)
        response = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['provider'], 'paystack')
        self.assertEqual(data['amount'], '15000.00')
        self.assertEqual(data['target_type'], 'sale')
        self.assertEqual(data['target_id'], self.sale.id)
        self.assertTrue(data['qr_data_uri'].startswith('data:image/svg+xml;base64,'))
        self.assertTrue(data['qr_svg'].startswith('<svg'))
        self.assertIn('expires_at', data)

        payment = Payment.objects.get(pk=data['payment_id'])
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.transaction_metadata['channel'], 'QR_CODE')
        self.assertEqual(payment.amount, Decimal('15000.00'))

    def test_customer_generates_qr_for_own_order(self):
        """Customer can generate dynamic QR code for their own order checkout."""
        self.client.force_login(self.customer)
        response = self.client.post(
            f'/payments/qr/order/{self.order.id}/generate/',
            data=json.dumps({'provider': 'moniepoint'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['provider'], 'moniepoint')
        self.assertEqual(data['amount'], '8500.00')
        self.assertEqual(data['target_type'], 'order')

    def test_qr_generation_idempotency_reuses_existing_pending_payment(self):
        """Repeated QR generation for the same sale reuses the existing pending payment record."""
        self.client.force_login(self.cashier)
        res1 = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        data1 = res1.json()['data']

        res2 = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        data2 = res2.json()['data']

        self.assertEqual(data1['payment_id'], data2['payment_id'])
        self.assertEqual(data1['payment_reference'], data2['payment_reference'])
        self.assertEqual(Payment.objects.filter(sale=self.sale).count(), 1)

    def test_customer_cannot_generate_qr_for_counter_pos_sale(self):
        """Customer role is blocked from generating QR for counter sales (403 Forbidden)."""
        self.client.force_login(self.customer)
        response = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_generate_qr_for_other_customer_order(self):
        """Customer is blocked from generating QR for another customer's order (403 Forbidden)."""
        self.client.force_login(self.other_customer)
        response = self.client.post(
            f'/payments/qr/order/{self.order.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated QR generation is rejected with 401 Unauthorized."""
        response = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_status_polling_endpoint_pending(self):
        """Status polling returns current PENDING status and verification state."""
        self.client.force_login(self.cashier)
        gen_res = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        ref = gen_res.json()['data']['payment_reference']

        status_res = self.client.get(f'/payments/qr/{ref}/status/')
        self.assertEqual(status_res.status_code, 200)
        data = status_res.json()['data']
        self.assertTrue(data['found'])
        self.assertEqual(data['status'], 'PENDING')
        self.assertFalse(data['is_completed'])

    def test_status_polling_endpoint_verified_via_mock(self):
        """Status polling reports VERIFIED when external provider confirms payment."""
        from unittest.mock import patch
        self.client.force_login(self.cashier)
        gen_res = self.client.post(
            f'/payments/qr/{self.sale.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        ref = gen_res.json()['data']['payment_reference']

        paystack_payload = {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'id': 888777,
                'status': 'success',
                'reference': gen_res.json()['data']['transaction_reference'],
                'amount': 1500000,
                'currency': 'NGN',
            },
        }

        class MockResp:
            def __init__(self, d):
                self.d = json.dumps(d).encode('utf-8')
            def getcode(self): return 200
            def read(self): return self.d
            def __enter__(self): return self
            def __exit__(self, exc_type, exc_val, exc_tb): pass

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': 'sk_test_fake123'}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', 'sk_test_fake123'), \
             patch('urllib.request.urlopen', return_value=MockResp(paystack_payload)):
            status_res = self.client.get(f'/payments/qr/{ref}/status/')
            self.assertEqual(status_res.status_code, 200)
            data = status_res.json()['data']
            self.assertTrue(data['is_verified'])

    def test_status_polling_customer_isolation(self):
        """Other customers cannot poll QR payment status for someone else's payment."""
        self.client.force_login(self.cashier)
        gen_res = self.client.post(
            f'/payments/qr/order/{self.order.id}/generate/',
            data=json.dumps({'provider': 'paystack'}),
            content_type='application/json',
        )
        ref = gen_res.json()['data']['payment_reference']

        self.client.force_login(self.other_customer)
        status_res = self.client.get(f'/payments/qr/{ref}/status/')
        self.assertEqual(status_res.status_code, 403)


class WebhookPaymentTests(TestCase):
    """Test Paystack and Moniepoint inbound webhook ingestion and double-payment guards."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username='webhook_customer',
            email='webhook_cust@example.com',
            password='StrongPassword123!',
            role='CUSTOMER',
        )
        self.cashier = User.objects.create_user(
            username='webhook_cashier',
            email='webhook_cashier@example.com',
            password='StrongPassword123!',
            role='CASHIER',
        )
        self.order = Order.objects.create(
            order_number='ORD-WH-001',
            customer=self.customer,
            subtotal=Decimal('8500.00'),
            total=Decimal('8500.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )
        self.sale = Sale.objects.create(
            sale_number='MH-SALE-WH-001',
            cashier=self.cashier,
            customer=self.customer,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
            payment_method=Sale.PaymentMethod.TRANSFER,
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.PENDING,
        )
        self.order_payment = Payment.objects.create(
            payment_reference='PAY-ORD-WH-001',
            transaction_reference='TXN-PSTK-WH-001',
            order=self.order,
            customer=self.customer,
            amount=Decimal('8500.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )
        self.sale_payment = Payment.objects.create(
            payment_reference='PAY-SALE-WH-001',
            transaction_reference='TXN-MNP-WH-001',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('15000.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.PENDING,
        )

    def test_paystack_webhook_valid_signature_confirms_payment(self):
        """Valid Paystack HMAC-SHA512 webhook confirms pending payment and advances order status."""
        import hashlib
        import hmac

        secret = 'sk_test_paystack_secret_wh'
        payload = {
            'event': 'charge.success',
            'data': {
                'id': 123456,
                'reference': self.order_payment.transaction_reference,
                'amount': 850000,
                'status': 'success',
                'currency': 'NGN',
            },
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            response = self.client.post(
                '/payments/webhooks/paystack/',
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['status'])
        self.assertEqual(data['data']['status'], 'completed')

        self.order_payment.refresh_from_db()
        self.assertEqual(self.order_payment.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertTrue(self.order_payment.transaction_metadata.get('webhook_confirmed'))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CONFIRMED)

    def test_paystack_webhook_invalid_signature_rejected(self):
        """Invalid Paystack signature is rejected with 400 Bad Request."""
        secret = 'sk_test_paystack_secret_wh'
        payload = {'event': 'charge.success', 'data': {'reference': self.order_payment.transaction_reference}}
        raw_body = json.dumps(payload).encode('utf-8')

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            response = self.client.post(
                '/payments/webhooks/paystack/',
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE='invalid_signature_hash',
            )

        self.assertEqual(response.status_code, 400)
        self.order_payment.refresh_from_db()
        self.assertEqual(self.order_payment.payment_status, Payment.PaymentStatus.PENDING)

    def test_paystack_webhook_missing_signature_rejected(self):
        """Missing Paystack signature header is rejected with 400 Bad Request."""
        payload = {'event': 'charge.success', 'data': {'reference': self.order_payment.transaction_reference}}
        response = self.client.post(
            '/payments/webhooks/paystack/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Missing', response.json()['message'])

    def test_moniepoint_webhook_valid_signature_confirms_payment(self):
        """Valid Moniepoint HMAC signature confirms pending payment and updates sale status."""
        import hashlib
        import hmac

        secret = 'mnp_secret_key_wh'
        payload = {
            'eventType': 'transaction.successful',
            'data': {
                'merchantReference': self.sale_payment.transaction_reference,
                'transactionReference': 'MNP-TXN-9988',
                'amount': 15000.00,
                'status': 'SUCCESSFUL',
                'currency': 'NGN',
            },
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        with patch.dict(os.environ, {'MONIEPOINT_SECRET_KEY': secret}), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', secret):
            response = self.client.post(
                '/payments/webhooks/moniepoint/',
                data=raw_body,
                content_type='application/json',
                HTTP_M_SIGNATURE=sig,
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['status'])
        self.assertEqual(data['data']['status'], 'completed')

        self.sale_payment.refresh_from_db()
        self.assertEqual(self.sale_payment.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertTrue(self.sale_payment.transaction_metadata.get('webhook_confirmed'))

        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.COMPLETED)

    def test_moniepoint_webhook_invalid_signature_rejected(self):
        """Invalid Moniepoint signature is rejected with 400 Bad Request."""
        secret = 'mnp_secret_key_wh'
        payload = {'eventType': 'transaction.successful', 'data': {'merchantReference': self.sale_payment.transaction_reference}}
        raw_body = json.dumps(payload).encode('utf-8')

        with patch.dict(os.environ, {'MONIEPOINT_SECRET_KEY': secret}), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', secret):
            response = self.client.post(
                '/payments/webhooks/moniepoint/',
                data=raw_body,
                content_type='application/json',
                HTTP_M_SIGNATURE='bad_signature_hash',
            )

        self.assertEqual(response.status_code, 400)
        self.sale_payment.refresh_from_db()
        self.assertEqual(self.sale_payment.payment_status, Payment.PaymentStatus.PENDING)

    def test_idempotency_guard_firing_webhook_twice_causes_zero_duplicate_mutations(self):
        """Firing identical webhook twice produces already_completed response with zero duplicates."""
        import hashlib
        import hmac

        secret = 'sk_test_paystack_secret_wh'
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': self.order_payment.transaction_reference,
                'amount': 850000,
                'status': 'success',
            },
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            res1 = self.client.post(
                '/payments/webhooks/paystack/',
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )
            self.assertEqual(res1.status_code, 200)
            self.assertEqual(res1.json()['data']['status'], 'completed')

            res2 = self.client.post(
                '/payments/webhooks/paystack/',
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(res2.json()['data']['status'], 'already_completed')

        self.assertEqual(Payment.objects.filter(pk=self.order_payment.pk).count(), 1)

    def test_amount_mismatch_protection_does_not_mark_completed(self):
        """Webhook with underpaid amount detects mismatch and refuses to auto-complete payment."""
        import hashlib
        import hmac

        secret = 'sk_test_paystack_secret_wh'
        # Expected 8500.00 (850,000 kobo), send 5000.00 (500,000 kobo)
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': self.order_payment.transaction_reference,
                'amount': 500000,
                'status': 'success',
            },
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            response = self.client.post(
                '/payments/webhooks/paystack/',
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['status'], 'amount_mismatch')
        self.assertTrue(data['has_discrepancy'])

        self.order_payment.refresh_from_db()
        self.assertEqual(self.order_payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertIn('Amount mismatch', self.order_payment.transaction_metadata.get('webhook_discrepancy', ''))
        self.assertEqual(self.order_payment.transaction_metadata.get('webhook_verification_status'), 'MISMATCH')

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_order_status_advancement_upon_webhook_payment_confirmation(self):
        """Direct confirmation via PaymentService.confirm_webhook_payment safely advances order lifecycle."""
        self.assertEqual(self.order.status, Order.OrderStatus.PENDING)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

        result = PaymentService.confirm_webhook_payment(
            reference=self.order_payment.transaction_reference,
            provider='paystack',
            payload={'event': 'charge.success'},
            paid_amount=Decimal('8500.00'),
            gateway_status='success',
        )

        self.assertEqual(result['status'], 'completed')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CONFIRMED)

    def test_webhook_failure_event_marks_payment_failed(self):
        """Webhook with failed status marks payment record FAILED."""
        result = PaymentService.confirm_webhook_payment(
            reference=self.order_payment.transaction_reference,
            provider='paystack',
            payload={'event': 'charge.failed'},
            paid_amount=Decimal('8500.00'),
            gateway_status='failed',
        )

        self.assertEqual(result['status'], 'failed')
        self.order_payment.refresh_from_db()
        self.assertEqual(self.order_payment.payment_status, Payment.PaymentStatus.FAILED)

    def test_webhook_audit_log_and_notification_dispatched(self):
        """Successful webhook payment confirmation creates both ActivityLog and in-app Notification."""
        from apps.notifications.models import Notification

        result = PaymentService.confirm_webhook_payment(
            reference=self.order_payment.transaction_reference,
            provider='paystack',
            payload={'event': 'charge.success'},
            paid_amount=Decimal('8500.00'),
            gateway_status='success',
        )
        self.assertEqual(result['status'], 'completed')

        notification = Notification.objects.filter(
            recipient=self.customer,
            notification_type=Notification.NotificationType.PAYMENT,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('Payment Confirmed', notification.title)

        log = ActivityLog.objects.filter(
            action_type=ActivityLog.ActionType.PAYMENT,
            metadata__reference=self.order_payment.payment_reference,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('provider'), 'paystack')


class PaymentResolutionTests(TestCase):
    """Test Phase 6 Discrepancy Resolution & Reconciliation Workflows."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='res_owner',
            email='res_owner@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='res_manager',
            email='res_manager@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='res_cashier',
            email='res_cashier@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            username='res_staff',
            email='res_staff@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='res_customer',
            email='res_customer@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )

        # Overpaid order & payment
        self.order_overpaid = Order.objects.create(
            order_number='ORD-RES-OVER-01',
            customer=self.customer,
            subtotal=Decimal('5000.00'),
            total=Decimal('5000.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )
        self.payment_overpaid = Payment.objects.create(
            payment_reference='PAY-RES-OVER-01',
            transaction_reference='TXN-RES-OVER-01',
            order=self.order_overpaid,
            customer=self.customer,
            amount=Decimal('6500.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        # Partially paid order & payment
        self.order_partial = Order.objects.create(
            order_number='ORD-RES-PART-01',
            customer=self.customer,
            subtotal=Decimal('10000.00'),
            total=Decimal('10000.00'),
            payment_method=Order.PaymentMethod.TRANSFER,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )
        self.payment_partial = Payment.objects.create(
            payment_reference='PAY-RES-PART-01',
            transaction_reference='TXN-RES-PART-01',
            order=self.order_partial,
            customer=self.customer,
            amount=Decimal('4000.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        # Mismatched order & payment
        self.order_mismatch = Order.objects.create(
            order_number='ORD-RES-MISMATCH-01',
            customer=self.customer,
            subtotal=Decimal('2000.00'),
            total=Decimal('2000.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )
        self.payment_mismatch = Payment.objects.create(
            payment_reference='PAY-RES-MISMATCH-01',
            transaction_reference='TXN-RES-MISMATCH-01',
            order=self.order_mismatch,
            customer=self.customer,
            amount=Decimal('2000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
            transaction_metadata={
                'verification_status': 'MISMATCH',
                'webhook_verification_status': 'MISMATCH',
                'webhook_discrepancy': 'Amount mismatch: expected 2000, received 1500',
            },
        )

    def test_resolve_overpaid_credit_customer_service(self):
        """Resolving an overpaid transaction with CREDIT_CUSTOMER credits excess to CustomerCreditAccount."""
        from apps.credits.models import CreditAccount, CreditTransaction
        from .resolution import PaymentResolutionService, ResolutionStrategy

        # Verify customer has no credit account initially
        self.assertFalse(CreditAccount.objects.filter(customer=self.customer).exists())

        result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_overpaid.id,
            strategy=ResolutionStrategy.CREDIT_CUSTOMER,
            actor=self.owner,
            resolution_notes='Crediting excess payment of 1500 to customer store credit account.',
        )

        self.assertEqual(result['status'], 'RESOLVED')
        self.assertEqual(result['strategy'], 'CREDIT_CUSTOMER')
        self.assertEqual(result['details']['credited_amount'], '1500.00')

        # Check credit account was created and credited
        credit_acc = CreditAccount.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(credit_acc)
        self.assertEqual(credit_acc.credit_limit, Decimal('1500.00'))
        self.assertEqual(credit_acc.outstanding_balance, Decimal('0.00'))

        # Check CreditTransaction ledger entry
        tx = CreditTransaction.objects.filter(credit_account=credit_acc).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('1500.00'))
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.ADJUSTMENT)

        # Check payment metadata
        self.payment_overpaid.refresh_from_db()
        self.assertEqual(self.payment_overpaid.transaction_metadata.get('resolution_status'), 'RESOLVED')
        self.assertEqual(self.payment_overpaid.transaction_metadata.get('resolved_by_username'), 'res_owner')

    def test_resolve_overpaid_credit_customer_pays_down_existing_debt(self):
        """CREDIT_CUSTOMER pays down existing outstanding debt first before adding credit allowance."""
        from django.utils import timezone
        from apps.credits.models import CreditAccount, CreditTransaction
        from .resolution import PaymentResolutionService, ResolutionStrategy

        credit_acc = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('5000.00'),
            outstanding_balance=Decimal('1000.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

        result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_overpaid.id,
            strategy=ResolutionStrategy.CREDIT_CUSTOMER,
            actor=self.manager,
            resolution_notes='Excess refund applied to clear outstanding debt balance.',
        )

        self.assertEqual(result['status'], 'RESOLVED')
        self.assertEqual(result['details']['repaid_debt'], '1000.00')
        self.assertEqual(result['details']['credit_allowance_added'], '500.00')

        credit_acc.refresh_from_db()
        self.assertEqual(credit_acc.outstanding_balance, Decimal('0.00'))
        self.assertEqual(credit_acc.credit_limit, Decimal('5500.00'))

    def test_resolve_partially_paid_complementary_payment(self):
        """Resolving PARTIALLY_PAID creates a complementary payment and clears transaction balance."""
        from .resolution import PaymentResolutionService, ResolutionStrategy

        result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_partial.id,
            strategy=ResolutionStrategy.RECORD_COMPLEMENTARY_PAYMENT,
            actor=self.manager,
            resolution_notes='Customer paid balance in cash at the counter.',
            payment_method=Payment.PaymentMethod.CASH,
        )

        self.assertEqual(result['status'], 'RESOLVED')
        self.assertEqual(result['details']['complementary_amount'], '6000.00')
        self.assertEqual(result['details']['remaining_outstanding'], '0.00')

        # Check complementary payment was created
        comp_id = result['details']['complementary_payment_id']
        comp_payment = Payment.objects.get(pk=comp_id)
        self.assertEqual(comp_payment.amount, Decimal('6000.00'))
        self.assertEqual(comp_payment.payment_method, Payment.PaymentMethod.CASH)
        self.assertEqual(comp_payment.payment_status, Payment.PaymentStatus.COMPLETED)

        # Target order should be advanced to CONFIRMED
        self.order_partial.refresh_from_db()
        self.assertEqual(self.order_partial.payment_status, Order.PaymentStatus.CONFIRMED)

        # Original payment metadata updated
        self.payment_partial.refresh_from_db()
        self.assertEqual(self.payment_partial.transaction_metadata.get('resolution_status'), 'RESOLVED')

    def test_resolve_manual_override_with_valid_notes(self):
        """MANUAL_OVERRIDE succeeds with detailed justification notes."""
        from .resolution import PaymentResolutionService, ResolutionStrategy

        result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_mismatch.id,
            strategy=ResolutionStrategy.MANUAL_OVERRIDE,
            actor=self.owner,
            resolution_notes='Administrative approval: discrepancy accepted per manager authorization.',
            mark_completed=True,
        )

        self.assertEqual(result['status'], 'RESOLVED')
        self.assertEqual(result['strategy'], 'MANUAL_OVERRIDE')

        self.payment_mismatch.refresh_from_db()
        self.assertEqual(self.payment_mismatch.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertEqual(self.payment_mismatch.transaction_metadata.get('resolution_status'), 'RESOLVED')
        self.assertEqual(self.payment_mismatch.transaction_metadata.get('webhook_verification_status'), 'RESOLVED')

    def test_resolve_manual_override_empty_notes_rejected(self):
        """Resolution without adequate resolution notes raises ValidationError."""
        from .resolution import PaymentResolutionService, ResolutionStrategy

        with self.assertRaises(ValidationError):
            PaymentResolutionService.resolve_discrepancy(
                payment_id_or_ref=self.payment_mismatch.id,
                strategy=ResolutionStrategy.MANUAL_OVERRIDE,
                actor=self.owner,
                resolution_notes='   ',
            )

        with self.assertRaises(ValidationError):
            PaymentResolutionService.resolve_discrepancy(
                payment_id_or_ref=self.payment_mismatch.id,
                strategy=ResolutionStrategy.MANUAL_OVERRIDE,
                actor=self.owner,
                resolution_notes='ok',  # less than 5 characters
            )

    def test_double_resolution_prevented(self):
        """Attempting to resolve an already-resolved payment raises ValidationError."""
        from .resolution import PaymentResolutionService, ResolutionStrategy

        PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_mismatch.id,
            strategy=ResolutionStrategy.MANUAL_OVERRIDE,
            actor=self.owner,
            resolution_notes='Initial resolution justification.',
        )

        with self.assertRaises(ValidationError) as ctx:
            PaymentResolutionService.resolve_discrepancy(
                payment_id_or_ref=self.payment_mismatch.id,
                strategy=ResolutionStrategy.MANUAL_OVERRIDE,
                actor=self.manager,
                resolution_notes='Attempting duplicate resolution.',
            )
        self.assertIn('already been resolved', str(ctx.exception))

    def test_rbac_resolve_endpoint(self):
        """POST /payments/<payment_id>/resolve/ allows OWNER and MANAGER; forbids CASHIER, STAFF, CUSTOMER."""
        url = f'/payments/{self.payment_mismatch.id}/resolve/'
        payload = {
            'strategy': 'MANUAL_OVERRIDE',
            'resolution_notes': 'Authorized resolution through RBAC testing.',
        }

        # Unauthenticated -> 401
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 401)

        # CASHIER -> 403
        self.client.force_login(self.cashier)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # STAFF -> 403
        self.client.force_login(self.staff)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # CUSTOMER -> 403
        self.client.force_login(self.customer)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # MANAGER -> 200 OK
        self.client.force_login(self.manager)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['data']['status'], 'RESOLVED')

    def test_rbac_mismatches_list_endpoint(self):
        """GET /payments/mismatches/ allows OWNER and MANAGER; forbids CASHIER, STAFF, CUSTOMER."""
        url = '/payments/mismatches/'

        # Unauthenticated -> 401
        res = self.client.get(url)
        self.assertEqual(res.status_code, 401)

        # CASHIER -> 403
        self.client.force_login(self.cashier)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # CUSTOMER -> 403
        self.client.force_login(self.customer)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # OWNER -> 200 OK
        self.client.force_login(self.owner)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertIn('discrepancies', data['data'])

    def test_mismatches_list_filtering(self):
        """GET /payments/mismatches/ filters by classification and resolution status."""
        self.client.force_login(self.owner)

        # Filter by classification OVERPAID
        res_overpaid = self.client.get('/payments/mismatches/?classification=OVERPAID')
        self.assertEqual(res_overpaid.status_code, 200)
        discrepancies = res_overpaid.json()['data']['discrepancies']
        for d in discrepancies:
            self.assertEqual(d['classification'], 'OVERPAID')

        # Filter by classification PARTIALLY_PAID
        res_partial = self.client.get('/payments/mismatches/?classification=PARTIALLY_PAID')
        self.assertEqual(res_partial.status_code, 200)
        discrepancies = res_partial.json()['data']['discrepancies']
        for d in discrepancies:
            self.assertEqual(d['classification'], 'PARTIALLY_PAID')

        # Filter by is_resolved=false vs is_resolved=true
        res_unresolved = self.client.get('/payments/mismatches/?is_resolved=false')
        self.assertEqual(res_unresolved.status_code, 200)
        for d in res_unresolved.json()['data']['discrepancies']:
            self.assertFalse(d['is_resolved'])

    def test_audit_log_and_notification_dispatched_on_resolution(self):
        """Resolving a discrepancy logs ActivityLog and creates an in-app Notification for customer."""
        from apps.notifications.models import Notification
        from .resolution import PaymentResolutionService, ResolutionStrategy

        PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=self.payment_mismatch.id,
            strategy=ResolutionStrategy.MANUAL_OVERRIDE,
            actor=self.owner,
            resolution_notes='Audited discrepancy resolution per management review.',
        )

        # Check ActivityLog
        audit_log = ActivityLog.objects.filter(
            action_type=ActivityLog.ActionType.UPDATED,
            metadata__payment_id=self.payment_mismatch.id,
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.metadata.get('strategy'), 'MANUAL_OVERRIDE')
        self.assertEqual(audit_log.metadata.get('resolved_by'), 'res_owner')

        # Check Notification
        notif = Notification.objects.filter(
            recipient=self.customer,
            notification_type=Notification.NotificationType.PAYMENT,
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('Discrepancy Resolved', notif.title)


class PaymentRefundTests(TestCase):
    """Test Phase 7 Payment Refunds, Chargebacks, & Multi-Channel Reversals."""

    def setUp(self):
        from django.utils import timezone
        from apps.credits.models import CreditAccount

        self.owner = User.objects.create_user(
            username='ref_owner',
            email='ref_owner@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='ref_manager',
            email='ref_manager@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='ref_cashier',
            email='ref_cashier@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            username='ref_staff',
            email='ref_staff@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='ref_customer',
            email='ref_customer@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )

        # Products and inventory item
        self.category = ProductCategory.objects.create(name='RefundCategory', slug='refund-cat')
        self.product = Product.objects.create(
            name='RefundProduct',
            slug='refund-prod',
            sku='REF-SKU-99',
            category=self.category,
            selling_price=Decimal('2500.00'),
            cost_price=Decimal('1500.00'),
            reorder_level=2,
        )
        self.inventory_item = InventoryItem.objects.create(product=self.product, quantity=10)

        # Standard online/card order & completed payment
        self.order = Order.objects.create(
            order_number='ORD-REF-TEST-01',
            customer=self.customer,
            subtotal=Decimal('5000.00'),
            total=Decimal('5000.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.CONFIRMED,
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('2500.00'),
            product_name_snapshot='RefundProduct',
            sku_snapshot='REF-SKU-99',
        )
        self.payment = Payment.objects.create(
            payment_reference='PAY-REF-TEST-01',
            transaction_reference='TXN-PSTK-REF-01',
            order=self.order,
            customer=self.customer,
            amount=Decimal('5000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        # Credit order & payment
        self.credit_acc = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('10000.00'),
            outstanding_balance=Decimal('4000.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        self.order_credit = Order.objects.create(
            order_number='ORD-REF-CRD-01',
            customer=self.customer,
            subtotal=Decimal('4000.00'),
            total=Decimal('4000.00'),
            payment_method=Order.PaymentMethod.CREDIT,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.CONFIRMED,
        )
        self.payment_credit = Payment.objects.create(
            payment_reference='PAY-REF-CRD-01',
            transaction_reference='TXN-CRD-REF-01',
            order=self.order_credit,
            customer=self.customer,
            amount=Decimal('4000.00'),
            payment_method=Payment.PaymentMethod.CREDIT,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

        # Cash order & payment
        self.order_cash = Order.objects.create(
            order_number='ORD-REF-CSH-01',
            customer=self.customer,
            subtotal=Decimal('3000.00'),
            total=Decimal('3000.00'),
            payment_method=Order.PaymentMethod.CASH,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.CONFIRMED,
        )
        self.payment_cash = Payment.objects.create(
            payment_reference='PAY-REF-CSH-01',
            transaction_reference='TXN-CSH-REF-01',
            order=self.order_cash,
            customer=self.customer,
            amount=Decimal('3000.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )

    def test_full_refund_with_inventory_restocking(self):
        """Full refund transitions payment to REFUNDED, cancels order, and restocks inventory with RETURN movement."""
        from apps.inventory.models import StockMovement
        from .refund_service import PaymentRefundService

        initial_stock = self.inventory_item.quantity
        result = PaymentRefundService.process_refund(
            payment=self.payment,
            reason='Customer requested full return of defective units.',
            restock_inventory=True,
            user=self.owner,
        )

        self.assertEqual(result['status'], 'REFUNDED')
        self.assertTrue(result['is_fully_refunded'])
        self.assertEqual(result['refund_amount'], '5000.00')
        self.assertEqual(result['total_refunded'], '5000.00')
        self.assertEqual(result['remaining_balance'], '0.00')
        self.assertTrue(result['restocked_inventory'])

        # Check inventory quantity incremented by 2
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock + 2)

        # Check StockMovement
        movement = StockMovement.objects.filter(
            inventory_item=self.inventory_item,
            movement_type=StockMovement.MovementType.RETURN,
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, 2)
        self.assertIn('REFUND-PAY-REF-TEST-01', movement.reference)

        # Check order status advanced to CANCELLED
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)

        # Check payment record state
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.REFUNDED)
        self.assertEqual(self.payment.total_refunded, Decimal('5000.00'))
        self.assertTrue(self.payment.is_fully_refunded)

    def test_partial_refund_amount_tracking_and_state(self):
        """Partial refund sets status to PARTIALLY_REFUNDED and tracks cumulative refund history."""
        from .refund_service import PaymentRefundService

        # First partial refund: 2000 of 5000
        res1 = PaymentRefundService.process_refund(
            payment=self.payment,
            amount=Decimal('2000.00'),
            reason='Partial item return.',
            user=self.manager,
        )
        self.assertEqual(res1['status'], 'PARTIALLY_REFUNDED')
        self.assertFalse(res1['is_fully_refunded'])
        self.assertEqual(res1['total_refunded'], '2000.00')
        self.assertEqual(res1['remaining_balance'], '3000.00')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.PARTIALLY_REFUNDED)
        self.assertEqual(self.payment.total_refunded, Decimal('2000.00'))
        self.assertEqual(self.payment.remaining_refundable_amount, Decimal('3000.00'))

        # Order remains confirmed during partial refund
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)

        # Second partial refund: remaining 3000
        res2 = PaymentRefundService.process_refund(
            payment=self.payment,
            amount=Decimal('3000.00'),
            reason='Refunded second item.',
            user=self.manager,
        )
        self.assertEqual(res2['status'], 'REFUNDED')
        self.assertTrue(res2['is_fully_refunded'])
        self.assertEqual(res2['total_refunded'], '5000.00')
        self.assertEqual(res2['remaining_balance'], '0.00')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.payment_status, Payment.PaymentStatus.REFUNDED)
        self.assertEqual(self.payment.total_refunded, Decimal('5000.00'))
        self.assertEqual(len(self.payment.transaction_metadata['refund_history']), 2)

        # Order transitions to CANCELLED upon final clearance
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)

    def test_over_refund_rejected(self):
        """Attempting to refund more than original amount or remaining refundable balance raises ValidationError."""
        from .refund_service import PaymentRefundService

        # Exceeding original total
        with self.assertRaises(ValidationError) as ctx:
            PaymentRefundService.process_refund(
                payment=self.payment,
                amount=Decimal('6000.00'),
                reason='Excess refund attempt.',
                user=self.owner,
            )
        self.assertIn('cannot exceed remaining refundable balance', str(ctx.exception))

        # Partial refund of 4000
        PaymentRefundService.process_refund(
            payment=self.payment,
            amount=Decimal('4000.00'),
            reason='Initial partial refund.',
            user=self.owner,
        )

        # Exceeding remaining 1000
        with self.assertRaises(ValidationError) as ctx:
            PaymentRefundService.process_refund(
                payment=self.payment,
                amount=Decimal('1500.00'),
                reason='Second excess attempt.',
                user=self.owner,
            )
        self.assertIn('cannot exceed remaining refundable balance', str(ctx.exception))

    def test_double_refund_prevented(self):
        """Attempting to refund an already fully refunded payment raises ValidationError."""
        from .refund_service import PaymentRefundService

        # Fully refund payment
        PaymentRefundService.process_refund(
            payment=self.payment,
            reason='Full refund initial pass.',
            user=self.owner,
        )

        # Duplicate refund attempt
        with self.assertRaises(ValidationError) as ctx:
            PaymentRefundService.process_refund(
                payment=self.payment,
                amount=Decimal('1000.00'),
                reason='Duplicate refund attempt.',
                user=self.owner,
            )
        self.assertIn('already been fully refunded', str(ctx.exception))

    def test_credit_channel_refund_adjusts_credit_account(self):
        """Credit payment refund reduces customer debt and writes an immutable CreditTransaction."""
        from apps.credits.models import CreditTransaction
        from .refund_service import PaymentRefundService

        self.assertEqual(self.credit_acc.outstanding_balance, Decimal('4000.00'))

        result = PaymentRefundService.process_refund(
            payment=self.payment_credit,
            amount=Decimal('2500.00'),
            reason='Customer cancelled credit purchase item.',
            user=self.manager,
        )

        self.assertEqual(result['status'], 'PARTIALLY_REFUNDED')
        self.assertEqual(result['channel'], 'CREDIT')

        self.credit_acc.refresh_from_db()
        self.assertEqual(self.credit_acc.outstanding_balance, Decimal('1500.00'))

        tx = CreditTransaction.objects.filter(payment=self.payment_credit).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('2500.00'))
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.ADJUSTMENT)

    def test_cash_channel_refund(self):
        """Cash payment refund records cash register reversal metadata."""
        from .refund_service import PaymentRefundService

        result = PaymentRefundService.process_refund(
            payment=self.payment_cash,
            amount=Decimal('3000.00'),
            reason='Counter return payout.',
            user=self.owner,
        )

        self.assertEqual(result['status'], 'REFUNDED')
        self.assertEqual(result['channel'], 'CASH')
        self.assertTrue(result['refund_entry']['channel_details']['cash_register_reversal'])

    def test_paystack_channel_refund_mock_adapter(self):
        """Paystack payment refund executes via mock adapter with deterministic gateway metadata."""
        from .refund_service import PaymentRefundService

        result = PaymentRefundService.process_refund(
            payment=self.payment,
            reason='Online refund requested via Paystack.',
            user=self.owner,
        )

        self.assertEqual(result['status'], 'REFUNDED')
        self.assertEqual(result['channel'], 'PAYSTACK')
        details = result['refund_entry']['channel_details']
        self.assertTrue(details['success'])
        self.assertEqual(details['provider'], 'paystack')
        self.assertIn('PSTK-REF-', details['refund_reference'])

    def test_rbac_refund_endpoint(self):
        """POST /payments/<payment_id>/refund/ allows OWNER and MANAGER; denies CASHIER, STAFF, CUSTOMER."""
        url = f'/payments/{self.payment.id}/refund/'
        payload = {
            'amount': '1500.00',
            'reason': 'RBAC authorization test.',
        }

        # Unauthenticated -> 401
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 401)

        # CASHIER -> 403
        self.client.force_login(self.cashier)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # STAFF -> 403
        self.client.force_login(self.staff)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # CUSTOMER -> 403
        self.client.force_login(self.customer)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 403)

        # MANAGER -> 200 OK
        self.client.force_login(self.manager)
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['data']['status'], 'PARTIALLY_REFUNDED')

    def test_rbac_refunds_list_endpoint(self):
        """GET /payments/refunds/ allows OWNER and MANAGER; denies CASHIER, STAFF, CUSTOMER."""
        url = '/payments/refunds/'

        # Unauthenticated -> 401
        res = self.client.get(url)
        self.assertEqual(res.status_code, 401)

        # CASHIER -> 403
        self.client.force_login(self.cashier)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # CUSTOMER -> 403
        self.client.force_login(self.customer)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 403)

        # OWNER -> 200 OK
        self.client.force_login(self.owner)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertIn('refunds', res.json()['data'])

    def test_audit_log_and_notification_dispatched_on_refund(self):
        """Refunding a payment records an ActivityLog audit entry and sends an in-app Notification."""
        from apps.notifications.models import Notification
        from .refund_service import PaymentRefundService

        PaymentRefundService.process_refund(
            payment=self.payment,
            amount=Decimal('1000.00'),
            reason='Customer return audit verification.',
            user=self.owner,
        )

        # ActivityLog check
        log = ActivityLog.objects.filter(
            action_type=ActivityLog.ActionType.UPDATED,
            metadata__payment_id=self.payment.id,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('status'), 'PARTIALLY_REFUNDED')
        self.assertEqual(log.metadata.get('refunded_by'), 'ref_owner')

        # Notification check
        notif = Notification.objects.filter(
            recipient=self.customer,
            notification_type=Notification.NotificationType.PAYMENT,
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('Refund Processed', notif.title)


class PaymentGatewayIntegrationAuditTests(TestCase):
    """
    Comprehensive tests for Dynamic QR Code Generation, Moniepoint POS Terminal Push/Polling,
    Moniepoint Webhooks, Paystack Checkout Initialization, and Webhook Verification.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='audit_owner', email='audit_owner@example.com', password='StrongPass123!', role='OWNER'
        )
        self.cashier = User.objects.create_user(
            username='audit_cashier', email='audit_cashier@example.com', password='StrongPass123!', role='CASHIER'
        )
        self.customer = User.objects.create_user(
            username='audit_customer', email='audit_customer@example.com', password='StrongPass123!', role='CUSTOMER'
        )
        self.category = ProductCategory.objects.create(name='Audit Bags', slug='audit-bags')
        self.product = Product.objects.create(
            name='Audited Shoulder Bag',
            category=self.category,
            selling_price=Decimal('15000.00'),
            cost_price=Decimal('10000.00'),
            sku='AUDIT-BAG-01',
            is_active=True,
        )
        self.inventory_item = InventoryItem.objects.create(
            product=self.product,
            quantity=50,
        )

        # Create draft sale
        self.sale = Sale.objects.create(
            sale_number='MH-AUDIT-SALE-001',
            customer=self.customer,
            cashier=self.cashier,
            subtotal=Decimal('30000.00'),
            total=Decimal('30000.00'),
            discount=Decimal('0.00'),
            payment_method=Sale.PaymentMethod.TRANSFER,
            status=Sale.SaleStatus.DRAFT,
            payment_status=Sale.PaymentStatus.PENDING,
        )
        self.sale_item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('15000.00'),
            product_name_snapshot=self.product.name,
            sku_snapshot=self.product.sku,
        )

        # Create pending order
        self.order = Order.objects.create(
            order_number='MH-AUDIT-ORD-001',
            customer=self.customer,
            created_by=self.cashier,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
            payment_method=Order.PaymentMethod.TRANSFER,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=Decimal('15000.00'),
            product_name_snapshot='Audited Shoulder Bag',
            sku_snapshot='AUDIT-BAG-01',
        )

    # 1. Dynamic QR Code Generation Tests
    def test_qr_code_generation(self):
        """Assert requesting payment intent returns valid Base64 data URI and SVG element."""
        from .qr_service import QRCodeService, generate_qr_svg, generate_qr_data_uri

        # Direct in-memory generators
        svg = generate_qr_svg('https://checkout.paystack.com/TXN-123')
        self.assertTrue(svg.startswith('<svg') or svg.startswith("<?xml"))
        self.assertIn('viewBox', svg)

        data_uri_svg = generate_qr_data_uri('https://checkout.paystack.com/TXN-123', image_format='svg')
        self.assertTrue(data_uri_svg.startswith('data:image/svg+xml;base64,'))

        data_uri_png = generate_qr_data_uri('https://checkout.paystack.com/TXN-123', image_format='png')
        self.assertTrue(data_uri_png.startswith('data:image/png;base64,'))

        # Empty payload guard
        with self.assertRaises(ValidationError):
            generate_qr_svg('')

        # Service-level get_or_create_qr_payment
        qr_result = QRCodeService.get_or_create_qr_payment(
            target=self.sale,
            provider='paystack',
            amount=Decimal('30000.00'),
            cashier=self.cashier,
        )
        self.assertEqual(qr_result['provider'], 'paystack')
        self.assertEqual(qr_result['amount'], '30000.00')
        self.assertTrue(qr_result['qr_code_svg'].startswith('<svg') or qr_result['qr_code_svg'].startswith("<?xml"))
        self.assertTrue(qr_result['qr_code_data_uri'].startswith('data:image/svg+xml;base64,'))
        self.assertTrue(qr_result['qr_data_uri'].startswith('data:image/svg+xml;base64,'))
        self.assertIn('checkout_url', qr_result)

        # API endpoint POST /payments/qr/generate/
        self.client.force_login(self.cashier)
        resp = self.client.post(
            reverse('payments:qr-generate'),
            data=json.dumps({
                'sale_id': self.sale.id,
                'provider': 'moniepoint',
                'amount': '30000.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['provider'], 'moniepoint')
        self.assertTrue(data['qr_code_svg'].startswith('<svg') or data['qr_code_svg'].startswith("<?xml"))
        self.assertTrue(data['qr_code_data_uri'].startswith('data:image/svg+xml;base64,'))

    # 2. Moniepoint Terminal Push Tests
    @patch('requests.get')
    @patch('requests.post')
    def test_moniepoint_terminal_push(self, mock_post, mock_get):
        """Mock Moniepoint API responses and assert successful terminal request dispatch and status recording."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': True,
            'responseCode': '00',
            'message': 'Terminal charge initiated successfully',
            'data': {'transactionReference': 'MNP-POS-TEST-9988'},
        }
        mock_post.return_value = mock_response

        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            'status': True,
            'responseCode': '00',
            'processingStatus': 'PENDING',
            'data': {'processingStatus': 'PENDING', 'amount': 3000000},
        }
        mock_get.return_value = mock_get_response

        # Service method call
        result = PaymentService.push_to_pos(
            target=self.sale,
            terminal_id='MP_TERM_AUDIT_01',
            amount=Decimal('30000.00'),
            cashier=self.cashier,
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['terminal_id'], 'MP_TERM_AUDIT_01')
        self.assertEqual(result['kobo_amount'], 3000000)
        self.assertEqual(result['status'], 'PENDING')

        payment = Payment.objects.get(pk=result['payment_id'])
        self.assertEqual(payment.payment_method, Payment.PaymentMethod.CARD)
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.transaction_metadata['terminal_push']['terminal_id'], 'MP_TERM_AUDIT_01')

        # Endpoint POST /payments/terminal/push/
        self.client.force_login(self.cashier)
        api_resp = self.client.post(
            reverse('payments:terminal-push'),
            data=json.dumps({
                'sale_id': self.sale.id,
                'terminal_id': 'MP_TERM_AUDIT_01',
                'amount': '30000.00',
            }),
            content_type='application/json',
        )
        self.assertEqual(api_resp.status_code, 200)
        self.assertTrue(api_resp.json()['success'])

        # Polling endpoint GET /payments/terminal/<reference>/status/
        poll_resp = self.client.get(
            reverse('payments:terminal-status', kwargs={'reference': payment.payment_reference})
        )
        self.assertEqual(poll_resp.status_code, 200)
        self.assertTrue(poll_resp.json()['data']['found'])

    # 3. Moniepoint Webhook Handling Tests
    def test_moniepoint_webhook_handling(self):
        """Test webhook payloads with valid and invalid signatures, asserting state updates and HTTP 200/400 responses."""
        secret = 'test_moniepoint_webhook_secret_key_123'
        payment = Payment.objects.create(
            payment_reference='PAY-MNP-WH-001',
            transaction_reference='TXN-MNP-WH-001',
            sale=self.sale,
            amount=Decimal('30000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        valid_payload = {
            'eventType': 'transaction.successful',
            'data': {
                'merchantReference': payment.transaction_reference,
                'transactionReference': 'MNP-POS-SWIPE-5566',
                'amount': 30000.00,
                'currency': 'NGN',
                'status': 'SUCCESSFUL',
            },
        }
        body_bytes = json.dumps(valid_payload).encode('utf-8')
        valid_sig = hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

        # 1. Invalid signature -> HTTP 400
        with patch.dict(os.environ, {'MONIEPOINT_SECRET_KEY': secret}), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', secret):
            bad_resp = self.client.post(
                reverse('payments:webhook-moniepoint'),
                data=body_bytes,
                content_type='application/json',
                HTTP_M_SIGNATURE='invalid_signature_string',
            )
            self.assertEqual(bad_resp.status_code, 400)
            self.assertFalse(bad_resp.json()['status'])
            self.assertIn('Invalid Moniepoint signature', bad_resp.json()['message'])

        # Payment remains pending after invalid signature
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)

        # 2. Valid signature -> HTTP 200, Payment COMPLETED, Sale COMPLETED, Inventory deducted
        initial_stock = self.inventory_item.quantity  # 50
        with patch.dict(os.environ, {'MONIEPOINT_SECRET_KEY': secret}), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', secret):
            good_resp = self.client.post(
                reverse('payments:webhook-moniepoint'),
                data=body_bytes,
                content_type='application/json',
                HTTP_M_SIGNATURE=f'sha256={valid_sig}',
            )
            self.assertEqual(good_resp.status_code, 200)
            self.assertTrue(good_resp.json()['status'])

        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)

        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.COMPLETED)
        self.assertEqual(self.sale.status, Sale.SaleStatus.COMPLETED)

        # Verify inventory was decremented atomically by 2 units
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock - 2)

    # 4. Paystack Checkout Initialization & Webhook Verification
    @patch('requests.post')
    def test_paystack_initialization_and_webhook(self, mock_post):
        """Test Paystack transaction initialization and webhook verification with order state transition."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': True,
            'message': 'Authorization URL created',
            'data': {
                'authorization_url': 'https://checkout.paystack.com/pstk_auth_url_123',
                'access_code': 'pstk_access_code_123',
                'reference': 'PSTK-TEST-ORD-REF',
            },
        }
        mock_post.return_value = mock_response

        # Service checkout initialization
        init_result = PaymentService.initialize_paystack_checkout(
            target=self.order,
            email='audit_customer@example.com',
            amount=Decimal('15000.00'),
        )
        self.assertTrue(init_result['success'])
        self.assertEqual(init_result['authorization_url'], 'https://checkout.paystack.com/pstk_auth_url_123')
        self.assertEqual(init_result['kobo_amount'], 1500000)

        # Webhook verification
        secret = 'test_paystack_secret_key_456'
        payment = Payment.objects.get(pk=init_result['payment_id'])
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)

        webhook_payload = {
            'event': 'charge.success',
            'data': {
                'reference': payment.payment_reference,
                'amount': 1500000,
                'currency': 'NGN',
                'status': 'success',
            },
        }
        body_bytes = json.dumps(webhook_payload).encode('utf-8')
        valid_sig = hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha512).hexdigest()

        # Invalid Paystack signature
        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            bad_resp = self.client.post(
                reverse('payments:webhook-paystack'),
                data=body_bytes,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE='bad_sig',
            )
            self.assertEqual(bad_resp.status_code, 400)

        # Valid Paystack signature
        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            good_resp = self.client.post(
                reverse('payments:webhook-paystack'),
                data=body_bytes,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=f'sha512={valid_sig}',
            )
            self.assertEqual(good_resp.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CONFIRMED)
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)


class DynamicPaymentQRCodeGenerationAndRoutingTests(TestCase):
    """
    Automated test verification for dynamic payment QR code generation,
    HTTPS URL routing, tunnel host resolution, and decoded QR payload validity.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='qr_owner_audit',
            password='Password123!',
            role=User.Role.OWNER,
            email='qr_owner_audit@example.com',
        )
        self.cashier = User.objects.create_user(
            username='qr_cashier_audit',
            password='Password123!',
            role=User.Role.CASHIER,
            email='qr_cashier_audit@example.com',
        )
        self.customer = User.objects.create_user(
            username='qr_customer_audit',
            password='Password123!',
            role=User.Role.CUSTOMER,
            email='qr_customer_audit@example.com',
        )
        self.sale = Sale.objects.create(
            sale_number='MH-SALE-QR-AUDIT-001',
            cashier=self.cashier,
            customer=self.customer,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
            payment_method=Sale.PaymentMethod.TRANSFER,
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.PENDING,
        )
        self.order = Order.objects.create(
            order_number='ORD-QR-AUDIT-001',
            customer=self.customer,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
            payment_method=Order.PaymentMethod.CARD,
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
        )

    def test_generate_payment_qr_returns_png_base64_and_valid_https_url(self):
        """
        Asserts that generate_payment_qr returns a string starting with
        data:image/png;base64, and that the decoded QR data string equals a valid,
        parseable https:// URL.
        """
        from apps.payments.services import generate_payment_qr, decode_qr_data

        test_https_url = 'https://checkout.paystack.com/QR-TEST-555?amount=1500000&currency=NGN'
        qr_str = generate_payment_qr(test_https_url)

        # 1. Assert string starts with data:image/png;base64,
        self.assertIsInstance(qr_str, str)
        self.assertTrue(
            qr_str.startswith('data:image/png;base64,'),
            f"Expected QR data URI to start with 'data:image/png;base64,', got: {qr_str[:30]}",
        )

        # 2. Decode QR data string and assert it equals valid parseable HTTPS URL
        decoded_url = decode_qr_data(qr_str)
        self.assertEqual(decoded_url, test_https_url)

        parsed = urllib.parse.urlparse(decoded_url)
        self.assertEqual(parsed.scheme, 'https')
        self.assertTrue(bool(parsed.netloc))
        self.assertIn('checkout.paystack.com', parsed.netloc)

    def test_generate_payment_qr_from_service_and_qr_module(self):
        """Verify generate_payment_qr can be imported from both services.py and qr_service.py."""
        from apps.payments.services import PaymentService, generate_payment_qr as svc_qr
        from apps.payments.qr_service import QRCodeService, generate_payment_qr as mod_qr, decode_qr_data

        url = 'https://checkout.paystack.com/TXN-XYZ-123'
        res1 = svc_qr(url)
        res2 = mod_qr(url)
        res3 = PaymentService.generate_payment_qr(url)
        res4 = QRCodeService.generate_payment_qr(url)

        for res in (res1, res2, res3, res4):
            self.assertTrue(res.startswith('data:image/png;base64,'))
            decoded = decode_qr_data(res)
            self.assertEqual(decoded, url)
            parsed = urllib.parse.urlparse(decoded)
            self.assertEqual(parsed.scheme, 'https')

    def test_generate_payment_qr_normalizes_relative_and_http_urls_to_https(self):
        """Relative paths and http://127.0.0.1 are normalized to valid https:// URLs."""
        from apps.payments.services import generate_payment_qr, decode_qr_data

        # Relative path normalization
        qr_rel = generate_payment_qr('/checkout/pay/TXN-999')
        self.assertTrue(qr_rel.startswith('data:image/png;base64,'))
        decoded_rel = decode_qr_data(qr_rel)
        parsed_rel = urllib.parse.urlparse(decoded_rel)
        self.assertEqual(parsed_rel.scheme, 'https')
        self.assertTrue(bool(parsed_rel.netloc))
        self.assertTrue(decoded_rel.endswith('/checkout/pay/TXN-999'))

        # HTTP localhost normalization
        qr_http = generate_payment_qr('http://127.0.0.1:8000/payments/pay/TXN-888')
        self.assertTrue(qr_http.startswith('data:image/png;base64,'))
        decoded_http = decode_qr_data(qr_http)
        parsed_http = urllib.parse.urlparse(decoded_http)
        self.assertEqual(parsed_http.scheme, 'https')
        self.assertTrue(bool(parsed_http.netloc))
        self.assertNotIn('http://', decoded_http)

    def test_tunnel_host_resolution_with_ngrok(self):
        """When operating behind a tunnel (ngrok), resolves base URL starting with https://<tunnel-host>."""
        from django.test import RequestFactory
        from apps.payments.qr_service import resolve_base_https_url, generate_payment_qr, decode_qr_data

        factory = RequestFactory()
        request = factory.get('/payments/qr/generate/', HTTP_HOST='abc123xyz.ngrok-free.app')

        base_url = resolve_base_https_url(request)
        self.assertEqual(base_url, 'https://abc123xyz.ngrok-free.app')

        qr_str = generate_payment_qr('/payments/pay/TXN-NGROK-001', request=request)
        self.assertTrue(qr_str.startswith('data:image/png;base64,'))
        decoded = decode_qr_data(qr_str)
        self.assertTrue(decoded.startswith('https://abc123xyz.ngrok-free.app/payments/pay/TXN-NGROK-001'))

    def test_generate_payment_qr_with_sale_and_order_models(self):
        """generate_payment_qr works with Sale and Order model instances."""
        from apps.payments.services import generate_payment_qr, decode_qr_data

        sale_qr = generate_payment_qr(self.sale)
        self.assertTrue(sale_qr.startswith('data:image/png;base64,'))
        sale_url = decode_qr_data(sale_qr)
        parsed_sale = urllib.parse.urlparse(sale_url)
        self.assertEqual(parsed_sale.scheme, 'https')
        self.assertTrue(bool(parsed_sale.netloc))

        order_qr = generate_payment_qr(self.order)
        self.assertTrue(order_qr.startswith('data:image/png;base64,'))
        order_url = decode_qr_data(order_qr)
        parsed_order = urllib.parse.urlparse(order_url)
        self.assertEqual(parsed_order.scheme, 'https')
        self.assertTrue(bool(parsed_order.netloc))

    def test_customer_qr_pay_view_renders_correctly(self):
        """Public mobile customer payment view renders checkout bill and fallback details."""
        from apps.payments.services import PaymentService

        payment = Payment.objects.create(
            payment_reference='QR-PSTK-SAL-99-TEST01',
            transaction_reference='TXN-QR-PSTK-TEST01',
            sale=self.sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('15000.00'),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.PENDING,
            transaction_metadata={
                'channel': 'QR_CODE',
                'details': {
                    'bank_name': 'Moniepoint MFB',
                    'account_number': '8012345678',
                },
            },
        )

        resp = self.client.get(f'/payments/pay/{payment.payment_reference}/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('Instant Payment Checkout', content)
        self.assertTrue('15000.00' in content or '15,000.00' in content)
        self.assertIn('Moniepoint MFB', content)
        self.assertIn('8012345678', content)
        self.assertIn('QR-PSTK-SAL-99-TEST01', content)
        self.assertIn('data:image/png;base64,', content)


class MoniepointPOSProductionIntegrationTests(TestCase):
    """
    Comprehensive test suite for Moniepoint POS integration in Madam HY Smart Shop.
    Covers:
      - Configuration validation (missing credentials, invalid terminal serial, URLs, timeouts)
      - Authentication (Direct API Key, OAuth Client Credentials, token exchange, caching, expiry, refresh)
      - Transaction Push (POST /v1/transactions, 202 acceptance, payload formats, error codes, retries)
      - Transaction Status (GET /v1/transactions/merchants/{ref}, SUCCESS, PENDING, FAILED, amount checks)
      - Business & Financial Integrity (Atomic sale completion, inventory deduction, idempotency)
      - Security & Role Isolation (Cashier permissions, customer data isolation)
    """

    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user(
            username='pos_cashier_prod',
            email='cashier_prod@example.com',
            password='CashierPass123!',
            role='CASHIER',
        )
        cls.customer = User.objects.create_user(
            username='pos_cust_prod',
            email='cust_prod@example.com',
            password='CustPass123!',
            role='CUSTOMER',
        )
        cls.other_customer = User.objects.create_user(
            username='pos_other_prod',
            email='other_prod@example.com',
            password='OtherPass123!',
            role='CUSTOMER',
        )
        cls.category = ProductCategory.objects.create(name='Bags')
        cls.product = Product.objects.create(
            name='Luxury Leather Handbag',
            sku='BAG-TEST-001',
            category=cls.category,
            selling_price=Decimal('25000.00'),
            cost_price=Decimal('15000.00'),
        )
        cls.inventory_item = InventoryItem.objects.create(
            product=cls.product,
            quantity=100,
        )

    def setUp(self):
        from apps.payments.terminal_service import MoniepointAuthManager
        MoniepointAuthManager.clear_cache()
        self.sale = Sale.objects.create(
            sale_number=f"MH-{uuid.uuid4().hex[:8].upper()}",
            cashier=self.cashier,
            customer=self.customer,
            subtotal=Decimal('50000.00'),
            total=Decimal('50000.00'),
            discount=Decimal('0.00'),
            status=Sale.SaleStatus.DRAFT,
            payment_status=Sale.PaymentStatus.PENDING,
            payment_method=Sale.PaymentMethod.CARD,
        )
        item = SaleItem.create_from_product(self.product, self.sale, quantity=2)
        item.save()

    # --------------------------------------------------------------------------
    # 1. Configuration Tests
    # --------------------------------------------------------------------------

    def test_missing_credentials_raises_configuration_error(self):
        """When neither API key nor OAuth client credentials are configured, raises MoniepointConfigurationError."""
        from apps.payments.terminal_service import MoniepointTerminalService, MoniepointConfigurationError
        with patch.dict(os.environ, {'MONIEPOINT_API_KEY': '', 'MONIEPOINT_CLIENT_ID': '', 'MONIEPOINT_SECRET_KEY': ''}), \
             patch('django.conf.settings.MONIEPOINT_API_KEY', ''), \
             patch('django.conf.settings.MONIEPOINT_CLIENT_ID', ''), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', ''):
            with self.assertRaises(MoniepointConfigurationError) as cm:
                MoniepointTerminalService.push_transaction(
                    terminal_serial='TERM-12345',
                    amount_naira=Decimal('1000.00'),
                    merchant_reference='POS-TEST-REF-001',
                )
            self.assertIn('API key is not configured', str(cm.exception))

    def test_invalid_terminal_serial_client_id_rejected(self):
        """When terminal_serial is mistakenly set to an API client ID string, raises ValidationError."""
        from apps.payments.terminal_service import MoniepointTerminalService
        with self.assertRaises(ValidationError) as cm:
            MoniepointTerminalService.push_transaction(
                terminal_serial='api-client-4985052-bc7c0560-1ea1-4edb-8790-4b8700d2f30f',
                amount_naira=Decimal('5000.00'),
                merchant_reference='POS-TEST-REF-002',
                api_key='mp_test_api_key_123',
            )
        self.assertIn('terminal_serial', cm.exception.message_dict)
        self.assertIn('API Client ID', cm.exception.message_dict['terminal_serial'][0])

    def test_empty_terminal_serial_rejected(self):
        """Empty terminal serial is rejected with ValidationError."""
        from apps.payments.terminal_service import MoniepointTerminalService
        with self.assertRaises(ValidationError) as cm:
            MoniepointTerminalService.push_transaction(
                terminal_serial='',
                amount_naira=Decimal('5000.00'),
                merchant_reference='POS-TEST-REF-003',
                api_key='mp_test_api_key_123',
            )
        self.assertIn('terminal_serial', cm.exception.message_dict)

    def test_zero_or_negative_amount_rejected(self):
        """Zero or negative amounts are rejected before sending to gateway."""
        from apps.payments.terminal_service import MoniepointTerminalService
        with self.assertRaises(ValidationError):
            MoniepointTerminalService.push_transaction(
                terminal_serial='TERM-12345',
                amount_naira=Decimal('0.00'),
                merchant_reference='POS-TEST-REF-004',
                api_key='mp_test_api_key_123',
            )
        with self.assertRaises(ValidationError):
            MoniepointTerminalService.push_transaction(
                terminal_serial='TERM-12345',
                amount_naira=Decimal('-500.00'),
                merchant_reference='POS-TEST-REF-005',
                api_key='mp_test_api_key_123',
            )

    # --------------------------------------------------------------------------
    # 2. Authentication Tests
    # --------------------------------------------------------------------------

    def test_direct_api_key_auth_header(self):
        """Direct API key is used as Bearer token in Authorization header."""
        from apps.payments.terminal_service import MoniepointAuthManager
        headers = MoniepointAuthManager.get_authorization_header(api_key='mp_live_direct_key_889')
        self.assertEqual(headers, {'Authorization': 'Bearer mp_live_direct_key_889'})

    @patch('requests.post')
    def test_oauth_client_credentials_token_exchange(self, mock_post):
        """OAuth client credentials exchange calls POST /v1/auth and returns Bearer token."""
        from apps.payments.terminal_service import MoniepointAuthManager
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'accessToken': 'oauth_bearer_jwt_token_12345',
            'expiresIn': 3600,
            'responseCode': '00',
        }
        mock_post.return_value = mock_resp

        headers = MoniepointAuthManager.get_authorization_header(
            client_id='api-client-test-id-01',
            client_secret='client-secret-xyz-99',
            base_url='https://channel.moniepoint.com',
        )
        self.assertEqual(headers, {'Authorization': 'Bearer oauth_bearer_jwt_token_12345'})
        mock_post.assert_called_once()
        self.assertIn('/v1/auth', mock_post.call_args[0][0])
        self.assertEqual(mock_post.call_args[1]['json']['username'], 'api-client-test-id-01')
        self.assertEqual(mock_post.call_args[1]['json']['password'], 'client-secret-xyz-99')

    @patch('requests.post')
    def test_oauth_token_caching_and_refresh(self, mock_post):
        """OAuth token is cached and reused until expired, then automatically refreshed."""
        from apps.payments.terminal_service import MoniepointAuthManager
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {'accessToken': 'token_round_1', 'expiresIn': 3600}
        mock_post.return_value = mock_resp1

        # First call obtains token
        h1 = MoniepointAuthManager.get_authorization_header(
            client_id='api-client-cache-test',
            client_secret='secret-1',
            base_url='https://channel.moniepoint.com',
        )
        self.assertEqual(h1, {'Authorization': 'Bearer token_round_1'})
        self.assertEqual(mock_post.call_count, 1)

        # Second call reuses cached token without another HTTP call
        h2 = MoniepointAuthManager.get_authorization_header(
            client_id='api-client-cache-test',
            client_secret='secret-1',
            base_url='https://channel.moniepoint.com',
        )
        self.assertEqual(h2, {'Authorization': 'Bearer token_round_1'})
        self.assertEqual(mock_post.call_count, 1)

        # Simulate expiration by setting cache expiry in the past
        cache_key = 'api-client-cache-test@https://channel.moniepoint.com'
        MoniepointAuthManager._token_cache[cache_key] = ('expired_token', 0)

        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {'accessToken': 'token_round_2_refreshed', 'expiresIn': 3600}
        mock_post.return_value = mock_resp2

        h3 = MoniepointAuthManager.get_authorization_header(
            client_id='api-client-cache-test',
            client_secret='secret-1',
            base_url='https://channel.moniepoint.com',
        )
        self.assertEqual(h3, {'Authorization': 'Bearer token_round_2_refreshed'})
        self.assertEqual(mock_post.call_count, 2)

    @patch('requests.post')
    def test_oauth_auth_failure_raises_error(self, mock_post):
        """When OAuth endpoint returns 401 Unauthorized, raises MoniepointAuthError."""
        from apps.payments.terminal_service import MoniepointAuthManager, MoniepointAuthError
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"message": "Invalid client credentials"}'
        mock_post.return_value = mock_resp

        with self.assertRaises(MoniepointAuthError) as cm:
            MoniepointAuthManager.get_authorization_header(
                client_id='invalid_client',
                client_secret='invalid_secret',
                base_url='https://channel.moniepoint.com',
            )
        self.assertIn('401', str(cm.exception))

    @patch('requests.post')
    def test_oauth_timeout_handling(self, mock_post):
        """When OAuth endpoint encounters a network timeout, raises MoniepointTimeoutError."""
        import requests as req
        from apps.payments.terminal_service import MoniepointAuthManager, MoniepointTimeoutError
        mock_post.side_effect = req.exceptions.Timeout('Connection to auth timed out')

        with self.assertRaises(MoniepointTimeoutError):
            MoniepointAuthManager.get_authorization_header(
                client_id='timeout_client',
                client_secret='timeout_secret',
                base_url='https://channel.moniepoint.com',
            )

    # --------------------------------------------------------------------------
    # 3. Transaction Push (POST /v1/transactions) Tests
    # --------------------------------------------------------------------------

    @patch('requests.post')
    def test_push_transaction_payload_and_http_202_accepted(self, mock_post):
        """Moniepoint push request formats payload in minor-unit kobo and accepts HTTP 202."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {'message': 'Transaction accepted for processing'}
        mock_post.return_value = mock_resp

        result = MoniepointTerminalService.push_transaction(
            terminal_serial='MP-POS-HW-9988',
            amount_naira=Decimal('50000.00'),
            merchant_reference='TXN-PUSH-001',
            payment_method='CARD_PURCHASE',
            api_key='mp_test_push_key',
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'PENDING')
        self.assertEqual(result['amount_kobo'], 5000000)  # 50,000 * 100
        self.assertEqual(result['amount_naira'], '50000.00')
        self.assertEqual(result['http_status'], 202)

        # Verify exact payload sent to provider
        call_kwargs = mock_post.call_args[1]
        sent_payload = call_kwargs['json']
        self.assertEqual(sent_payload['terminalSerial'], 'MP-POS-HW-9988')
        self.assertEqual(sent_payload['amount'], 5000000)
        self.assertEqual(sent_payload['merchantReference'], 'TXN-PUSH-001')
        self.assertEqual(sent_payload['transactionType'], 'PURCHASE')
        self.assertEqual(sent_payload['paymentMethod'], 'CARD_PURCHASE')

        # Verify Authorization header
        sent_headers = call_kwargs['headers']
        self.assertEqual(sent_headers['Authorization'], 'Bearer mp_test_push_key')

    @patch('requests.post')
    def test_push_transaction_http_400_error(self, mock_post):
        """HTTP 400 Bad Request from gateway is handled gracefully without throwing unhandled exceptions."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {'message': 'Terminal not registered or offline'}
        mock_post.return_value = mock_resp

        result = MoniepointTerminalService.push_transaction(
            terminal_serial='MP-OFFLINE-TERM',
            amount_naira=Decimal('50000.00'),
            merchant_reference='TXN-PUSH-ERR-400',
            api_key='mp_test_push_key',
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['http_status'], 400)
        self.assertEqual(result['message'], 'Terminal not registered or offline')

    @patch('requests.post')
    def test_push_transaction_timeout_handled_gracefully(self, mock_post):
        """Network timeout during push returns clean failure dictionary."""
        import requests as req
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_post.side_effect = req.exceptions.Timeout('Socket timed out')

        result = MoniepointTerminalService.push_transaction(
            terminal_serial='MP-POS-HW-9988',
            amount_naira=Decimal('50000.00'),
            merchant_reference='TXN-PUSH-TIMEOUT',
            api_key='mp_test_push_key',
            max_retries=0,
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('Socket timed out', str(result['error']))

    # --------------------------------------------------------------------------
    # 4. Transaction Status (GET /v1/transactions/merchants/{ref}) Tests
    # --------------------------------------------------------------------------

    @patch('requests.get')
    def test_status_query_success_with_minor_unit_kobo(self, mock_get):
        """Status endpoint parsing successful transaction with amount in kobo."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'SUCCESSFUL',
                'actualAmount': 5000000,  # ₦50,000 in kobo
                'responseCode': '00',
                'responseMessage': 'Approved',
                'terminalSerial': 'MP-POS-HW-9988',
                'rrn': '000123456789',
                'transactionReference': 'MNP-GW-REF-99',
                'merchantReference': 'TXN-QUERY-SUCCESS',
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.get_transaction_status(
            merchant_reference='TXN-QUERY-SUCCESS',
            api_key='mp_test_key',
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['actual_amount_naira'], '50000.00')
        self.assertEqual(result['actual_amount_kobo'], 5000000)
        self.assertEqual(result['terminal_serial'], 'MP-POS-HW-9988')
        self.assertEqual(result['rrn'], '000123456789')

    @patch('requests.get')
    def test_status_query_processed_with_error_code_classified_failed(self, mock_get):
        """PROCESSED status with an error responseCode is not blindly trusted as success."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'PROCESSED',
                'actualAmount': 5000000,
                'responseCode': '99',  # Error code
                'responseMessage': 'Declined by issuer',
                'merchantReference': 'TXN-DECLINED-99',
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.get_transaction_status(
            merchant_reference='TXN-DECLINED-99',
            api_key='mp_test_key',
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'FAILED')

    @patch('requests.get')
    def test_status_query_pending_and_queued(self, mock_get):
        """PENDING or QUEUED status maps to PENDING."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'PENDING',
                'merchantReference': 'TXN-PENDING-01',
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.get_transaction_status(
            merchant_reference='TXN-PENDING-01',
            api_key='mp_test_key',
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'PENDING')

    @patch('requests.get')
    def test_status_query_http_404_treated_as_pending(self, mock_get):
        """HTTP 404 from status query represents a transaction not yet seen by gateway; treated as PENDING."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {'message': 'Transaction not found'}
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.get_transaction_status(
            merchant_reference='TXN-NOT-FOUND-YET',
            api_key='mp_test_key',
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'PENDING')
        self.assertEqual(result['processing_status'], 'NOT_FOUND')

    @patch('requests.get')
    def test_status_query_reference_mismatch_detected(self, mock_get):
        """When returned merchantReference does not match queried reference, classified as FAILED."""
        from apps.payments.terminal_service import MoniepointTerminalService
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'SUCCESSFUL',
                'merchantReference': 'SOME_OTHER_REF_999',
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.get_transaction_status(
            merchant_reference='EXPECTED_REF_111',
            api_key='mp_test_key',
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'FAILED')
        self.assertTrue(result['reference_mismatch'])

    # --------------------------------------------------------------------------
    # 5. Business & Financial Integrity Tests
    # --------------------------------------------------------------------------

    @patch('requests.get')
    def test_poll_terminal_status_completes_sale_and_deducts_inventory(self, mock_get):
        """
        On confirmed terminal payment:
        - Payment transitions to COMPLETED
        - Sale transitions to COMPLETED
        - Inventory is decremented by exact item quantity
        - StockMovement is recorded with STOCK_OUT
        """
        from apps.inventory.models import StockMovement
        from apps.payments.terminal_service import MoniepointTerminalService

        initial_stock = self.inventory_item.quantity  # 100
        payment = Payment.objects.create(
            payment_reference='PAY-POS-TEST-001',
            transaction_reference='TXN-POS-TEST-001',
            sale=self.sale,
            amount=Decimal('50000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'SUCCESSFUL',
                'actualAmount': 5000000,
                'responseCode': '00',
                'terminalSerial': 'MP-TERM-001',
                'rrn': '000987654321',
                'transactionReference': 'MNP-TXN-SUCCESS-99',
                'merchantReference': payment.transaction_reference,
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.poll_terminal_status(
            reference=payment.transaction_reference,
            cashier=self.cashier,
            api_key='mp_test_key',
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertTrue(result['is_completed'])

        # Verify payment transitioned to COMPLETED
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)

        # Verify sale transitioned to COMPLETED
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.SaleStatus.COMPLETED)
        self.assertEqual(self.sale.payment_status, Sale.PaymentStatus.COMPLETED)

        # Verify physical inventory was decremented by 2 units (from 100 to 98)
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock - 2)

        # Verify StockMovement record was created
        movements = StockMovement.objects.filter(
            inventory_item=self.inventory_item,
            movement_type='STOCK_OUT',
            reference=self.sale.sale_number,
        )
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().quantity, -2)

    @patch('requests.get')
    def test_repeated_polling_is_idempotent_no_duplicate_deduction(self, mock_get):
        """Repeated polling of a completed payment does NOT deduct inventory twice."""
        from apps.inventory.models import StockMovement
        from apps.payments.terminal_service import MoniepointTerminalService

        initial_stock = self.inventory_item.quantity  # 100
        payment = Payment.objects.create(
            payment_reference='PAY-POS-IDEMP-001',
            transaction_reference='TXN-POS-IDEMP-001',
            sale=self.sale,
            amount=Decimal('50000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'SUCCESSFUL',
                'actualAmount': 5000000,
                'responseCode': '00',
                'merchantReference': payment.transaction_reference,
            }
        }
        mock_get.return_value = mock_resp

        # Poll 1
        res1 = MoniepointTerminalService.poll_terminal_status(
            reference=payment.transaction_reference,
            cashier=self.cashier,
            api_key='mp_test_key',
        )
        self.assertTrue(res1['success'])

        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock - 2)

        # Poll 2 (Immediate retry / repeated polling)
        res2 = MoniepointTerminalService.poll_terminal_status(
            reference=payment.transaction_reference,
            cashier=self.cashier,
            api_key='mp_test_key',
        )
        self.assertTrue(res2['success'])

        # Inventory MUST remain at 98, not 96
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock - 2)

        # Movement count remains 1
        self.assertEqual(
            StockMovement.objects.filter(inventory_item=self.inventory_item, movement_type='STOCK_OUT').count(),
            1,
        )

    @patch('requests.get')
    def test_amount_mismatch_blocks_sale_completion(self, mock_get):
        """If gateway returns an amount different from sale amount, payment is not completed and stock is not deducted."""
        from apps.payments.terminal_service import MoniepointTerminalService

        initial_stock = self.inventory_item.quantity  # 100
        payment = Payment.objects.create(
            payment_reference='PAY-POS-MISMATCH-001',
            transaction_reference='TXN-POS-MISMATCH-001',
            sale=self.sale,
            amount=Decimal('50000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'processingStatus': 'SUCCESSFUL',
                'actualAmount': 1000000,  # ₦10,000 instead of ₦50,000
                'responseCode': '00',
                'merchantReference': payment.transaction_reference,
            }
        }
        mock_get.return_value = mock_resp

        result = MoniepointTerminalService.poll_terminal_status(
            reference=payment.transaction_reference,
            cashier=self.cashier,
            api_key='mp_test_key',
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'MISMATCH')

        # Payment remains PENDING
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)

        # Sale remains DRAFT
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.SaleStatus.DRAFT)

        # Inventory NOT deducted
        self.inventory_item.refresh_from_db()
        self.assertEqual(self.inventory_item.quantity, initial_stock)

    # --------------------------------------------------------------------------
    # 6. View & Security Role Isolation Tests
    # --------------------------------------------------------------------------

    def test_terminal_push_endpoint_requires_staff_role(self):
        """Customers and unauthenticated users cannot initiate terminal push charges."""
        # Unauthenticated -> 401
        resp_unauth = self.client.post(
            reverse('payments:terminal-push'),
            data={'sale_id': self.sale.id},
        )
        self.assertEqual(resp_unauth.status_code, 401)

        # Customer -> 403
        self.client.force_login(self.customer)
        resp_cust = self.client.post(
            reverse('payments:terminal-push'),
            data={'sale_id': self.sale.id},
        )
        self.assertEqual(resp_cust.status_code, 403)

    @patch('requests.get')
    def test_terminal_status_endpoint_enforces_customer_isolation(self, mock_get):
        """Customers cannot inspect terminal status for sales that do not belong to them."""
        payment = Payment.objects.create(
            payment_reference='PAY-POS-ISO-001',
            transaction_reference='TXN-POS-ISO-001',
            sale=self.sale,
            customer=self.customer,
            amount=Decimal('50000.00'),
            payment_method=Payment.PaymentMethod.CARD,
            payment_status=Payment.PaymentStatus.PENDING,
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {'processingStatus': 'PENDING', 'merchantReference': payment.transaction_reference}
        }
        mock_get.return_value = mock_resp

        # Other customer -> 403 Forbidden
        self.client.force_login(self.other_customer)
        resp_other = self.client.get(
            reverse('payments:terminal-status', kwargs={'reference': payment.transaction_reference})
        )
        self.assertEqual(resp_other.status_code, 403)

        # Cashier -> 200 OK
        self.client.force_login(self.cashier)
        resp_cashier = self.client.get(
            reverse('payments:terminal-status', kwargs={'reference': payment.transaction_reference})
        )
        self.assertEqual(resp_cashier.status_code, 200)
        self.assertTrue(resp_cashier.json()['success'])
