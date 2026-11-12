import hashlib
import hmac
import json
import os
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.credits.models import CreditAccount, CreditTransaction
from apps.credits.services import CreditService
from apps.inventory.models import InventoryItem, StockMovement
from apps.inventory.services import adjust_inventory_stock
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.payments.qr_service import QRCodeService
from apps.payments.refund_service import PaymentRefundService, RefundChannel
from apps.payments.resolution import PaymentResolutionService, ResolutionStrategy
from apps.payments.services import PaymentService
from apps.products.models import ProductCategory, Product
from apps.sales.models import Sale, SaleItem

User = get_user_model()


class SystemIntegrationPassTests(TestCase):
    """
    Section 17: Comprehensive End-to-End System Invariant Verification.
    Validates complete multi-step business lifecycles across Customer Storefront,
    POS Counter Sales with QR, Payment Webhooks with Idempotency, Credit Operations
    with Overpayment Resolution, and Order Cancellation with Multi-Channel Refunds.
    """

    def setUp(self):
        self.client = Client()

        # Actors across roles
        self.owner = User.objects.create_user(
            username='integ_owner',
            email='owner@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='integ_manager',
            email='manager@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='integ_cashier',
            email='cashier@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            username='integ_customer',
            email='customer@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
            first_name='Amara',
            last_name='Eze',
        )

        # Catalog setup
        self.category = ProductCategory.objects.create(name='Skincare & Cosmetics', description='Premium beauty')
        self.product1 = Product.objects.create(
            name='Hydrating Rose Serum',
            slug='hydrating-rose-serum',
            sku='HRS-001',
            category=self.category,
            selling_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00'),
            is_active=True,
        )
        self.inv1 = InventoryItem.objects.create(
            product=self.product1,
            quantity=100,
        )

        self.product2 = Product.objects.create(
            name='Mineral Glow Sunscreen',
            slug='mineral-glow-sunscreen',
            sku='MGS-002',
            category=self.category,
            selling_price=Decimal('7500.00'),
            cost_price=Decimal('4500.00'),
            is_active=True,
            reorder_level=5,
        )
        self.inv2 = InventoryItem.objects.create(
            product=self.product2,
            quantity=60,
        )

    # ==========================================================================
    # WORKFLOW 1: Customer Online Order -> Paystack Webhook -> Order Conversion
    # ==========================================================================

    def test_workflow_1_customer_online_order_paystack_webhook_and_idempotency(self):
        """
        Workflow 1:
        1. Customer logs in and checks out items from online catalog.
        2. Order is created in PENDING status; session cart is cleared.
        3. Pending Payment record is created for the order.
        4. Valid Paystack HMAC-SHA512 webhook arrives; transitions Payment to COMPLETED,
           Order to CONFIRMED, creates customer Notification, and writes ActivityLog.
        5. Manager fulfills order by converting it to Sale; inventory is decremented atomically.
        6. Second identical Paystack webhook is fired: handled idempotently with zero duplicate
           stock deductions or duplicate payments.
        """
        # 1. Customer checkout
        self.client.force_login(self.customer)
        checkout_payload = {
            'items': [
                {'product_id': self.product1.id, 'quantity': 2},  # 2 * 5,000 = 10,000
                {'product_id': self.product2.id, 'quantity': 1},  # 1 * 7,500 = 7,500
            ],
            'payment_method': 'CARD',
            'delivery_address': '45 Victoria Island, Lagos',
            'customer_phone': '+2348011223344',
            'notes': 'Deliver during working hours.',
        }
        checkout_resp = self.client.post(
            reverse('customer_orders:checkout'),
            data=json.dumps(checkout_payload),
            content_type='application/json',
        )
        self.assertEqual(checkout_resp.status_code, 201)
        checkout_data = checkout_resp.json()
        self.assertTrue(checkout_data['success'])
        order_id = checkout_data['data']['order']['id']

        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.status, Order.OrderStatus.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(order.total, Decimal('17500.00'))
        self.assertEqual(order.items.count(), 2)

        # Verify initial inventory remains untouched before conversion
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 100)
        self.assertEqual(self.inv2.quantity, 60)

        # 2. Attach pending payment for Paystack checkout
        payment = Payment.objects.filter(order=order).first()
        if not payment:
            payment = Payment.objects.create(
                order=order,
                customer=self.customer,
                amount=order.total,
                payment_reference=f'PAY-PSTK-{order.order_number}',
                payment_method=Payment.PaymentMethod.BANK_TRANSFER,
                payment_status=Payment.PaymentStatus.PENDING,
                transaction_reference=f'PSTK-{order.order_number}',
            )
        else:
            payment.transaction_reference = f'PSTK-{order.order_number}'
            payment.payment_method = Payment.PaymentMethod.BANK_TRANSFER
            payment.save(update_fields=['transaction_reference', 'payment_method'])

        # 3. Simulate inbound Paystack Webhook with valid HMAC-SHA512
        secret = 'sk_test_paystack_secret_integration_pass'
        webhook_payload = {
            'event': 'charge.success',
            'data': {
                'id': 987654321,
                'reference': payment.transaction_reference,
                'amount': 1750000,  # 17,500 NGN in kobo
                'status': 'success',
                'currency': 'NGN',
            },
        }
        raw_body = json.dumps(webhook_payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()

        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            webhook_resp = self.client.post(
                reverse('payments:webhook-paystack'),
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        self.assertEqual(webhook_resp.status_code, 200)
        resp_data = webhook_resp.json()
        self.assertTrue(resp_data['status'])
        self.assertEqual(resp_data['data']['status'], 'completed')

        # Verify Payment and Order transitions
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertTrue(payment.transaction_metadata.get('webhook_confirmed'))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CONFIRMED)

        # Verify customer notification was created
        notif = Notification.objects.filter(recipient=self.customer, notification_type=Notification.NotificationType.PAYMENT).latest('created_at')
        self.assertIn('17,500.00', notif.message)
        self.assertEqual(notif.title, 'Payment Confirmed')

        # Verify audit activity log entry
        audit_log = ActivityLog.objects.filter(object_id=payment.id).latest('created_at')
        self.assertEqual(audit_log.action_label, 'Webhook payment confirmed')

        # 4. Fulfill Order by converting to Sale
        self.client.force_login(self.manager)
        convert_resp = self.client.post(
            f'/orders/{order.id}/convert-to-sale/',
        )
        self.assertEqual(convert_resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertTrue(hasattr(order, 'sale'))
        sale = order.sale
        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)

        # Verify stock was deducted upon conversion
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 98)  # 100 - 2
        self.assertEqual(self.inv2.quantity, 59)  # 60 - 1

        # Verify StockMovement records
        movements = StockMovement.objects.filter(reference=sale.sale_number)
        self.assertEqual(movements.count(), 2)
        self.assertTrue(all(m.movement_type == 'STOCK_OUT' for m in movements))

        # 5. Idempotency Guard: Fire identical webhook a second time
        with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}), \
             patch('django.conf.settings.PAYSTACK_SECRET_KEY', secret):
            dup_resp = self.client.post(
                reverse('payments:webhook-paystack'),
                data=raw_body,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=sig,
            )

        self.assertEqual(dup_resp.status_code, 200)
        self.assertIn('already completed', dup_resp.json()['message'].lower())

        # Verify zero duplicate stock deductions or payment records
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 98)
        self.assertEqual(self.inv2.quantity, 59)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(StockMovement.objects.filter(reference=sale.sale_number).count(), 2)

    # ==========================================================================
    # WORKFLOW 2: POS Counter Sale -> Dynamic QR -> Moniepoint Webhook
    # ==========================================================================

    def test_workflow_2_counter_pos_sale_dynamic_qr_moniepoint_webhook_completion(self):
        """
        Workflow 2:
        1. Cashier rings up multiple items at POS terminal, creating a DRAFT sale.
        2. Cashier generates dynamic in-store QR code via Moniepoint provider.
        3. Valid Moniepoint HMAC webhook confirms payment received.
        4. Payment is marked COMPLETED; Sale payment_status becomes COMPLETED.
        5. Cashier completes the sale; inventory is decremented atomically, receipt is generated.
        """
        self.client.force_login(self.cashier)

        # 1. Ring up items at POS terminal
        sale_payload = {
            'customer_id': self.customer.id,
            'payment_method': 'TRANSFER',
            'discount': '0.00',
            'items': [
                {'product_id': self.product1.id, 'quantity': 3},  # 3 * 5,000 = 15,000
                {'product_id': self.product2.id, 'quantity': 2},  # 2 * 7,500 = 15,000
            ],
            'notes': 'POS Counter transaction with QR payment',
        }
        create_resp = self.client.post(
            reverse('sales:create'),
            data=json.dumps(sale_payload),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 200)
        sale_id = create_resp.json()['data']['sale']['id']

        sale = Sale.objects.get(pk=sale_id)
        self.assertEqual(sale.status, Sale.SaleStatus.DRAFT)
        self.assertEqual(sale.total, Decimal('30000.00'))

        # Verify inventory has NOT been decremented yet in DRAFT state
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 100)
        self.assertEqual(self.inv2.quantity, 60)

        # 2. Cashier generates in-store dynamic QR code
        qr_resp = self.client.post(
            f'/payments/qr/{sale.id}/generate/?provider=moniepoint',
        )
        self.assertEqual(qr_resp.status_code, 200)
        qr_data = qr_resp.json()['data']
        self.assertEqual(qr_data['provider'], 'moniepoint')
        self.assertTrue(qr_data['qr_svg'].startswith('<svg'))
        self.assertTrue(qr_data['qr_data_uri'].startswith('data:image/svg+xml;base64,'))
        self.assertEqual(Decimal(qr_data['amount']), Decimal('30000.00'))

        # Verify pending Payment record created
        payment = Payment.objects.get(pk=qr_data['payment_id'])
        self.assertEqual(payment.sale, sale)
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.transaction_metadata.get('channel'), 'QR_CODE')

        # 3. Simulate inbound Moniepoint webhook
        secret = 'mnp_secret_key_integration_pass'
        moniepoint_payload = {
            'eventType': 'transaction.successful',
            'data': {
                'merchantReference': payment.transaction_reference,
                'transactionReference': 'MNP-POS-QR-778899',
                'amount': 30000.00,
                'status': 'SUCCESSFUL',
                'currency': 'NGN',
            },
        }
        raw_body = json.dumps(moniepoint_payload).encode('utf-8')
        sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        with patch.dict(os.environ, {'MONIEPOINT_SECRET_KEY': secret}), \
             patch('django.conf.settings.MONIEPOINT_SECRET_KEY', secret):
            webhook_resp = self.client.post(
                reverse('payments:webhook-moniepoint'),
                data=raw_body,
                content_type='application/json',
                HTTP_M_SIGNATURE=sig,
            )

        self.assertEqual(webhook_resp.status_code, 200)
        self.assertTrue(webhook_resp.json()['status'])

        # Verify Payment and Sale payment status
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.COMPLETED)
        self.assertTrue(payment.transaction_metadata.get('webhook_confirmed'))

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.COMPLETED)

        # 4. Cashier finalizes POS sale completion
        complete_resp = self.client.post(
            reverse('sales:complete', kwargs={'sale_id': sale.id}),
            data=json.dumps({'amount_received': '30000.00'}),
            content_type='application/json',
        )
        self.assertEqual(complete_resp.status_code, 200)
        completed_data = complete_resp.json()['data']
        self.assertEqual(completed_data['status'], Sale.SaleStatus.COMPLETED)
        self.assertEqual(completed_data['payment_status'], Sale.PaymentStatus.COMPLETED)

        # Verify inventory was decremented atomically
        self.inv1.refresh_from_db()
        self.inv2.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 97)  # 100 - 3
        self.assertEqual(self.inv2.quantity, 58)  # 60 - 2

        # Verify StockMovement records
        movements = StockMovement.objects.filter(reference=sale.sale_number)
        self.assertEqual(movements.count(), 2)
        self.assertTrue(all(m.movement_type == 'STOCK_OUT' for m in movements))

    # ==========================================================================
    # WORKFLOW 3: Customer Credit Purchase -> Repayment -> Overpayment Resolution
    # ==========================================================================

    def test_workflow_3_credit_purchase_repayment_and_overpayment_resolution(self):
        """
        Workflow 3:
        1. Customer has approved CreditAccount (credit limit: 50,000, balance: 0).
        2. Customer purchases 20,000 worth of goods on credit; debt increases, available credit decreases.
        3. Customer submits partial repayment of 5,000; debt reduces to 15,000.
        4. Customer submits overpayment repayment of 25,000 (10,000 excess).
        5. PaymentResolutionService (CREDIT_CUSTOMER) clears outstanding debt down to 0 first,
           then expands customer credit limit with the remaining 10,000 excess.
        """
        # 1. Setup approved credit account
        credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        self.assertEqual(credit_account.get_available_credit(), Decimal('50000.00'))

        # 2. Make credit purchase of 20,000 (4 * 5,000)
        self.client.force_login(self.cashier)
        sale_payload = {
            'customer_id': self.customer.id,
            'payment_method': 'CREDIT',
            'discount': '0.00',
            'items': [{'product_id': self.product1.id, 'quantity': 4}],
            'notes': 'Credit purchase on account',
        }
        create_resp = self.client.post(
            reverse('sales:create'),
            data=json.dumps(sale_payload),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 200)
        sale_id = create_resp.json()['data']['sale']['id']

        # Complete credit sale
        complete_resp = self.client.post(
            reverse('sales:complete', kwargs={'sale_id': sale_id}),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(complete_resp.status_code, 200)

        credit_account.refresh_from_db()
        self.assertEqual(credit_account.outstanding_balance, Decimal('20000.00'))
        self.assertEqual(credit_account.get_available_credit(), Decimal('30000.00'))

        # 3. Partial repayment of 5,000
        sale = Sale.objects.get(pk=sale_id)
        repay_payment = Payment.objects.create(
            sale=sale,
            customer=self.customer,
            amount=Decimal('5000.00'),
            payment_reference=f'PAY-REPAY-{uuid.uuid4().hex[:8].upper()}',
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='CRD-REPAY-001',
        )
        credit_account.record_repayment(
            amount=Decimal('5000.00'),
            payment=repay_payment,
            created_by=self.cashier,
            notes='Partial counter cash repayment',
        )
        credit_account.refresh_from_db()
        self.assertEqual(credit_account.outstanding_balance, Decimal('15000.00'))
        self.assertEqual(credit_account.get_available_credit(), Decimal('35000.00'))

        # 4. Inbound overpayment repayment of 25,000 (debt is 15,000; excess is 10,000)
        overpay_payment = Payment.objects.create(
            sale=sale,
            customer=self.customer,
            amount=Decimal('25000.00'),
            payment_reference=f'PAY-OVERPAY-{uuid.uuid4().hex[:8].upper()}',
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='CRD-OVERPAY-002',
            transaction_metadata={'has_discrepancy': True, 'discrepancy': 'Customer overpaid credit debt by 10,000'},
        )

        # 5. Manager executes PaymentResolutionService (CREDIT_CUSTOMER)
        resolution_result = PaymentResolutionService.resolve_discrepancy(
            payment_id_or_ref=overpay_payment.id,
            strategy=ResolutionStrategy.CREDIT_CUSTOMER,
            actor=self.manager,
            resolution_notes='Clear remaining 15k debt and allocate 10k excess to increase customer credit limit.',
            amount=Decimal('25000.00'),
        )
        self.assertEqual(resolution_result['status'], 'RESOLVED')

        credit_account.refresh_from_db()
        # Outstanding balance must be cleared to 0
        self.assertEqual(credit_account.outstanding_balance, Decimal('0.00'))
        # Credit limit must be expanded from 50,000 + 10,000 excess = 60,000
        self.assertEqual(credit_account.credit_limit, Decimal('60000.00'))
        self.assertEqual(credit_account.get_available_credit(), Decimal('60000.00'))

        # Verify CreditTransaction audit entries
        txns = CreditTransaction.objects.filter(credit_account=credit_account).order_by('-created_at')
        self.assertTrue(txns.filter(transaction_type=CreditTransaction.TransactionType.REPAYMENT).exists())
        self.assertTrue(txns.filter(transaction_type=CreditTransaction.TransactionType.ADJUSTMENT).exists())

    # ==========================================================================
    # WORKFLOW 4: Order Cancellation & Multi-Channel Refund with Restocking
    # ==========================================================================

    def test_workflow_4_order_cancellation_and_multichannel_refund_with_restocking(self):
        """
        Workflow 4:
        1. Customer places order and completes payment.
        2. Order is confirmed, converted to sale, and stock is decremented.
        3. Manager executes full refund via PaymentRefundService with restock_inventory=True.
        4. Verifies Payment transitions to REFUNDED, Order transitions to CANCELLED,
           Sale transitions to CANCELLED, stock is restocked via StockMovement(RETURN),
           and customer Notification is dispatched.
        5. Subsequent refund attempt on the same payment is rejected with ValidationError.
        """
        # 1. Place and confirm order
        order = Order.objects.create(
            order_number=f'ORD-REFUND-{uuid.uuid4().hex[:6].upper()}',
            customer=self.customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.TRANSFER,
            payment_status=Order.PaymentStatus.CONFIRMED,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
        )
        item1 = OrderItem.create_from_product(
            product=self.product1,
            order=order,
            quantity=3,
        )
        item1.save()

        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=Decimal('15000.00'),
            payment_reference=f'PAY-REFUND-{uuid.uuid4().hex[:8].upper()}',
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference=f'TXN-PSTK-REFUND-{uuid.uuid4().hex[:6]}',
        )

        # Convert order to sale and deduct inventory
        sale = Sale.objects.create(
            sale_number=f'MH-SALE-REFUND-{uuid.uuid4().hex[:6].upper()}',
            source_order=order,
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.DRAFT,
            payment_method=Sale.PaymentMethod.TRANSFER,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('15000.00'),
            total=Decimal('15000.00'),
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product1,
            quantity=3,
            unit_price=Decimal('5000.00'),
            product_name_snapshot=self.product1.name,
            sku_snapshot=self.product1.sku,
        )
        # Deduct inventory for sale
        adjust_inventory_stock(
            inventory_item=self.inv1,
            quantity_delta=-3,
            movement_type='STOCK_OUT',
            reference=sale.sale_number,
            created_by=self.cashier,
        )
        sale.status = Sale.SaleStatus.COMPLETED
        sale.save()

        self.inv1.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 97)  # 100 - 3

        # 2. Manager processes full refund with restock_inventory=True
        refund_result = PaymentRefundService.process_refund(
            payment=payment,
            amount=Decimal('15000.00'),
            reason='Customer requested full order cancellation and return.',
            restock_inventory=True,
            user=self.manager,
            channel=RefundChannel.PAYSTACK,
        )
        self.assertEqual(refund_result['status'], Payment.PaymentStatus.REFUNDED)
        self.assertTrue(refund_result['is_fully_refunded'])
        self.assertEqual(refund_result['total_refunded'], '15000.00')

        # 3. Verify Payment and Order states
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.REFUNDED)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)

        # 4. Verify inventory was restocked back to 100 via StockMovement(RETURN)
        self.inv1.refresh_from_db()
        self.assertEqual(self.inv1.quantity, 100)

        return_movement = StockMovement.objects.filter(
            inventory_item=self.inv1,
            movement_type=StockMovement.MovementType.RETURN,
        ).latest('created_at')
        self.assertEqual(return_movement.quantity, 3)
        self.assertIn('Refund restock', return_movement.reason)

        # 5. Verify customer notification dispatched
        notif = Notification.objects.filter(
            recipient=self.customer,
            notification_type=Notification.NotificationType.PAYMENT,
        ).latest('created_at')
        self.assertIn('refund of NGN 15000.00', notif.message)
        self.assertEqual(notif.title, 'Payment Refund Processed')

        # 6. Verify subsequent refund attempts are rejected
        with self.assertRaises(ValidationError) as ctx:
            PaymentRefundService.process_refund(
                payment=payment,
                amount=Decimal('5000.00'),
                reason='Attempt duplicate refund on already refunded payment.',
                user=self.manager,
            )
        self.assertIn('already been fully refunded', str(ctx.exception))
