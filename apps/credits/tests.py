from decimal import Decimal
import json

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.accounts.models import User
from apps.inventory.models import InventoryItem
from apps.payments.models import Payment
from apps.products.models import Product, ProductCategory
from apps.sales.models import Sale
from .models import CreditAccount, CreditTransaction
from .services import CreditService


class CreditAccountModelTests(TestCase):
    """Tests for the Credits backend foundation."""

    def setUp(self):
        self.category = ProductCategory.objects.create(name='Fashion', slug='fashion')
        self.product = Product.objects.create(
            name='Premium Ankara Fabric',
            slug='premium-ankara-fabric',
            sku='FAB-001',
            category=self.category,
            selling_price=Decimal('18000.00'),
            cost_price=Decimal('12000.00'),
        )
        InventoryItem.objects.create(product=self.product, quantity=20)

        self.owner = User.objects.create_user(
            email='owner@example.com',
            username='owner',
            first_name='Ada',
            last_name='Owner',
            password='StrongPass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='manager@example.com',
            username='manager',
            first_name='Mira',
            last_name='Manager',
            password='StrongPass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            first_name='Cleo',
            last_name='Cashier',
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
        self.customer2 = User.objects.create_user(
            email='customer2@example.com',
            username='customer2',
            first_name='Jane',
            last_name='Doe',
            password='StrongPass123',
            role='CUSTOMER',
        )

    def test_customer_credit_account_creation(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('200000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
            next_due_date=timezone.now().date(),
        )
        self.assertEqual(account.customer, self.customer)
        self.assertEqual(account.credit_limit, Decimal('200000.00'))
        self.assertEqual(account.outstanding_balance, Decimal('0.00'))

    def test_only_customer_can_have_credit_account(self):
        account = CreditAccount(
            customer=self.owner,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_one_credit_account_per_customer(self):
        CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('200000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

        with self.assertRaises(Exception):
            CreditAccount.objects.create(
                customer=self.customer,
                credit_limit=Decimal('300000.00'),
                outstanding_balance=Decimal('0.00'),
                status=CreditAccount.Status.APPROVED,
                approved_by=self.owner,
                approved_at=timezone.now(),
            )

    def test_credit_limit_validation(self):
        account = CreditAccount(
            customer=self.customer,
            credit_limit=Decimal('-100.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            account.full_clean()

    def test_available_credit_calculation(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('250000.00'),
            outstanding_balance=Decimal('70000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.manager,
            approved_at=timezone.now(),
        )
        self.assertEqual(account.get_available_credit(), Decimal('180000.00'))
        self.assertTrue(account.can_use_credit(Decimal('150000.00')))
        self.assertFalse(account.can_use_credit(Decimal('200000.00')))

    def test_credit_purchase_with_valid_allowance(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('300000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1001',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('12000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        tx = account.record_credit_purchase(
            sale=sale,
            amount=Decimal('12000.00'),
            created_by=self.owner,
            reference='CREDIT-PURCHASE-1',
            notes='Credit sale recorded.',
        )

        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.CREDIT_PURCHASE)
        self.assertEqual(account.outstanding_balance, Decimal('12000.00'))
        self.assertEqual(tx.previous_balance, Decimal('0.00'))
        self.assertEqual(tx.new_balance, Decimal('12000.00'))

    def test_credit_purchase_without_allowance_rejected(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('0.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.PENDING_APPROVAL,
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1002',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('5000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('5000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-2',
            )

    def test_credit_purchase_exceeding_allowance_rejected(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('20000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1003',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('30000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('40000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-3',
            )

    def test_sale_customer_mismatch_rejected(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('100000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1004',
            customer=self.customer2,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('15000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('15000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-4',
            )

    def test_repayment_reduces_balance_and_updates_last_payment_date(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('200000.00'),
            outstanding_balance=Decimal('80000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
            next_due_date=timezone.now().date(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1012',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('80000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )
        payment = Payment.objects.create(
            payment_reference='PMT-CRED-1001',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('20000.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-REP-1',
        )

        tx = account.record_repayment(
            amount=Decimal('20000.00'),
            payment=payment,
            created_by=self.owner,
            reference='REPAY-1',
            notes='Customer repayment',
        )

        self.assertEqual(account.outstanding_balance, Decimal('60000.00'))
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.REPAYMENT)
        self.assertEqual(account.last_payment_date, timezone.now().date())

    def test_repayment_cannot_exceed_balance(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('15000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            account.record_repayment(
                amount=Decimal('20000.00'),
                created_by=self.owner,
                reference='REPAY-2',
            )

    def test_due_date_and_overdue_detection(self):
        old_date = timezone.now().date().replace(day=1)
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('40000.00'),
            outstanding_balance=Decimal('10000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
            next_due_date=old_date,
        )
        self.assertTrue(account.is_overdue())
        self.assertEqual(account.get_status_for_balance(), CreditAccount.Status.OVERDUE)

    def test_suspended_account_cannot_make_credit_purchase(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.SUSPENDED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1005',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('20000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('20000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-5',
            )

    def test_closed_account_cannot_make_credit_purchase(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.CLOSED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1006',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('15000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('15000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-6',
            )

    def test_transaction_preserves_previous_and_new_balance(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('100000.00'),
            outstanding_balance=Decimal('15000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1007',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('10000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        tx = account.record_credit_purchase(
            sale=sale,
            amount=Decimal('10000.00'),
            created_by=self.owner,
            reference='CREDIT-PURCHASE-7',
        )

        self.assertEqual(tx.previous_balance, Decimal('15000.00'))
        self.assertEqual(tx.new_balance, Decimal('25000.00'))

    def test_historical_credit_transaction_is_protected_from_deletion(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1008',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('5000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )
        tx = account.record_credit_purchase(
            sale=sale,
            amount=Decimal('5000.00'),
            created_by=self.owner,
            reference='CREDIT-PURCHASE-8',
        )

        with self.assertRaises(ValidationError):
            tx.delete()

    def test_credits_does_not_modify_inventory_or_product_data(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1009',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('6000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        original_quantity = self.product.inventory_item.quantity
        original_price = self.product.selling_price

        account.record_credit_purchase(
            sale=sale,
            amount=Decimal('6000.00'),
            created_by=self.owner,
            reference='CREDIT-PURCHASE-9',
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_item.quantity, original_quantity)
        self.assertEqual(self.product.selling_price, original_price)

    def test_credits_does_not_duplicate_payment_records(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('10000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1013',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CASH,
            total=Decimal('10000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )
        payment = Payment.objects.create(
            payment_reference='PMT-CRED-1002',
            sale=sale,
            customer=self.customer,
            cashier=self.cashier,
            amount=Decimal('5000.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
            transaction_reference='TXN-REP-2',
        )

        tx = account.record_repayment(
            amount=Decimal('5000.00'),
            payment=payment,
            created_by=self.owner,
            reference='REPAY-3',
        )

        self.assertEqual(tx.payment, payment)
        self.assertEqual(Payment.objects.filter(payment_reference='PMT-CRED-1002').count(), 1)

    def test_atomic_behavior_prevents_partial_updates(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('10000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1010',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('60000.00'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        before_balance = account.outstanding_balance
        before_count = CreditTransaction.objects.count()

        with self.assertRaises(ValidationError):
            account.record_credit_purchase(
                sale=sale,
                amount=Decimal('50000.00'),
                created_by=self.owner,
                reference='CREDIT-PURCHASE-10',
            )

        account.refresh_from_db()
        self.assertEqual(account.outstanding_balance, before_balance)
        self.assertEqual(CreditTransaction.objects.count(), before_count)

    def test_decimal_precision_is_preserved(self):
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('10000.75'),
            outstanding_balance=Decimal('0.00'),
            status=CreditAccount.Status.APPROVED,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        sale = Sale.objects.create(
            sale_number='MH-CRD-1011',
            customer=self.customer,
            cashier=self.cashier,
            payment_method=Sale.PaymentMethod.CREDIT,
            total=Decimal('1250.50'),
            status=Sale.SaleStatus.COMPLETED,
            payment_status=Sale.PaymentStatus.COMPLETED,
        )

        tx = account.record_credit_purchase(
            sale=sale,
            amount=Decimal('1250.50'),
            created_by=self.owner,
            reference='CREDIT-PURCHASE-11',
        )

        self.assertEqual(account.outstanding_balance, Decimal('1250.50'))
        self.assertEqual(tx.new_balance, Decimal('1250.50'))

    def test_django_system_checks_pass(self):
        call_command('check')


class CreditServiceRepaymentTests(TestCase):
    """Unit tests for CreditService.process_repayment service logic and integrity."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner_svc@example.com',
            username='owner_svc',
            first_name='Ada',
            last_name='Owner',
            password='StrongPass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='manager_svc@example.com',
            username='manager_svc',
            first_name='Mira',
            last_name='Manager',
            password='StrongPass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='cashier_svc@example.com',
            username='cashier_svc',
            first_name='Cleo',
            last_name='Cashier',
            password='StrongPass123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='cust_svc@example.com',
            username='cust_svc',
            first_name='Aisha',
            last_name='Bello',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('20000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.manager,
            approved_at=timezone.now(),
        )

    def test_process_repayment_success(self):
        initial_balance = self.account.outstanding_balance
        repay_amount = Decimal('5000.00')

        tx, updated_account = CreditService.process_repayment(
            credit_account=self.account,
            amount=repay_amount,
            payment_method='CASH',
            created_by=self.cashier,
            reference='REC-CASH-001',
            notes='Paid at counter',
        )

        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.REPAYMENT)
        self.assertEqual(tx.amount, repay_amount)
        self.assertEqual(tx.previous_balance, initial_balance)
        self.assertEqual(tx.new_balance, Decimal('15000.00'))
        self.assertEqual(tx.created_by, self.cashier)
        self.assertEqual(tx.reference, 'REC-CASH-001')

        self.account.refresh_from_db()
        self.assertEqual(self.account.outstanding_balance, Decimal('15000.00'))
        self.assertEqual(self.account.last_payment_date, timezone.now().date())

        # Audit log verification
        log = ActivityLog.objects.filter(
            actor=self.cashier,
            action_type=ActivityLog.ActionType.PAYMENT,
        ).first()
        self.assertIsNotNone(log)
        self.assertIn('repayment', log.action_label.lower())
        self.assertEqual(log.metadata.get('repayment_amount'), '5000.00')
        self.assertEqual(log.metadata.get('payment_method'), 'CASH')

    def test_process_repayment_clears_balance_sets_approved_status(self):
        tx, updated_account = CreditService.process_repayment(
            credit_account=self.account,
            amount=Decimal('20000.00'),
            payment_method='BANK_TRANSFER',
            created_by=self.manager,
            reference='TXN-FULL-CLEAR',
        )

        self.assertEqual(updated_account.outstanding_balance, Decimal('0.00'))
        self.assertEqual(updated_account.status, CreditAccount.Status.APPROVED)
        self.account.refresh_from_db()
        self.assertEqual(self.account.outstanding_balance, Decimal('0.00'))
        self.assertEqual(self.account.status, CreditAccount.Status.APPROVED)

    def test_process_repayment_rejects_negative_or_zero_amount(self):
        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('0.00'),
                payment_method='CASH',
                created_by=self.cashier,
            )
        self.assertIn('amount', ctx.exception.message_dict)

        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('-500.00'),
                payment_method='CASH',
                created_by=self.cashier,
            )
        self.assertIn('amount', ctx.exception.message_dict)

    def test_process_repayment_rejects_amount_exceeding_outstanding_balance(self):
        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('25000.00'),
                payment_method='CASH',
                created_by=self.cashier,
            )
        self.assertIn('amount', ctx.exception.message_dict)

    def test_process_repayment_rejects_invalid_payment_method(self):
        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('1000.00'),
                payment_method='CREDIT',
                created_by=self.cashier,
            )
        self.assertIn('payment_method', ctx.exception.message_dict)

        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('1000.00'),
                payment_method='CRYPTO',
                created_by=self.cashier,
            )
        self.assertIn('payment_method', ctx.exception.message_dict)

    def test_process_repayment_accepts_and_normalizes_methods(self):
        # TRANSFER -> BANK_TRANSFER
        tx1, _ = CreditService.process_repayment(
            credit_account=self.account,
            amount=Decimal('1000.00'),
            payment_method='transfer',
            created_by=self.cashier,
        )
        self.assertIn('BANK_TRANSFER', tx1.notes)

        # POS -> CARD
        tx2, _ = CreditService.process_repayment(
            credit_account=self.account,
            amount=Decimal('1000.00'),
            payment_method='POS',
            created_by=self.cashier,
        )
        self.assertIn('CARD', tx2.notes)

    def test_process_repayment_rejects_unauthorized_created_by_role(self):
        with self.assertRaises(ValidationError) as ctx:
            CreditService.process_repayment(
                credit_account=self.account,
                amount=Decimal('1000.00'),
                payment_method='CASH',
                created_by=self.customer,
            )
        self.assertIn('created_by', ctx.exception.message_dict)


class CreditRepaymentWorkflowHTTPTests(TestCase):
    """End-to-end integration and HTTP endpoint tests for credit repayments, listing, and detail."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner_http@example.com',
            username='owner_http',
            first_name='Ada',
            last_name='Owner',
            password='StrongPass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='manager_http@example.com',
            username='manager_http',
            first_name='Mira',
            last_name='Manager',
            password='StrongPass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='cashier_http@example.com',
            username='cashier_http',
            first_name='Cleo',
            last_name='Cashier',
            password='StrongPass123',
            role='CASHIER',
        )
        self.staff_member = User.objects.create_user(
            email='staff_http@example.com',
            username='staff_http',
            first_name='Sam',
            last_name='Staff',
            password='StrongPass123',
            role='STAFF',
        )
        self.customer1 = User.objects.create_user(
            email='cust1_http@example.com',
            username='cust1_http',
            first_name='Emeka',
            last_name='Ibe',
            phone_number='08011112222',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.customer2 = User.objects.create_user(
            email='cust2_http@example.com',
            username='cust2_http',
            first_name='Grace',
            last_name='Nnaji',
            phone_number='08033334444',
            password='StrongPass123',
            role='CUSTOMER',
        )

        self.account1 = CreditAccount.objects.create(
            customer=self.customer1,
            credit_limit=Decimal('100000.00'),
            outstanding_balance=Decimal('40000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.manager,
            approved_at=timezone.now(),
            next_due_date=timezone.now().date() + timezone.timedelta(days=14),
        )
        self.account2 = CreditAccount.objects.create(
            customer=self.customer2,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('15000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
            next_due_date=timezone.now().date() - timezone.timedelta(days=2),  # overdue
        )

    # --------------------------------------------------------------------------
    # Repayment Endpoint Tests
    # --------------------------------------------------------------------------

    def test_unauthenticated_repay_denied_401(self):
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})
        response = self.client.post(
            url,
            data=json.dumps({'amount': '5000.00', 'payment_method': 'CASH'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_customer_cannot_record_repayment_denied_403(self):
        self.client.force_login(self.customer1)
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})
        # Customer trying to repay their own account via staff endpoint
        response = self.client.post(
            url,
            data=json.dumps({'amount': '5000.00', 'payment_method': 'CASH'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

        # Customer trying to repay another customer's account
        url2 = reverse('credits:credit_repay', kwargs={'account_id': self.account2.id})
        response2 = self.client.post(
            url2,
            data=json.dumps({'amount': '5000.00', 'payment_method': 'CASH'}),
            content_type='application/json',
        )
        self.assertEqual(response2.status_code, 403)

    def test_cashier_can_record_repayment_200(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})
        response = self.client.post(
            url,
            data=json.dumps({
                'amount': '10000.00',
                'payment_method': 'CASH',
                'reference': 'RCPT-0091',
                'notes': 'Paid in person at counter',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['data']['account']['outstanding_balance'], '30000.00')
        self.assertEqual(res_data['data']['transaction']['amount'], '10000.00')
        self.assertEqual(res_data['data']['transaction']['previous_balance'], '40000.00')
        self.assertEqual(res_data['data']['transaction']['new_balance'], '30000.00')

        self.account1.refresh_from_db()
        self.assertEqual(self.account1.outstanding_balance, Decimal('30000.00'))

    def test_manager_and_owner_can_record_repayment_200(self):
        # Manager
        self.client.force_login(self.manager)
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})
        resp_mgr = self.client.post(
            url,
            data=json.dumps({'amount': '5000.00', 'payment_method': 'BANK_TRANSFER'}),
            content_type='application/json',
        )
        self.assertEqual(resp_mgr.status_code, 200)

        # Owner
        self.client.force_login(self.owner)
        resp_owner = self.client.post(
            url,
            data=json.dumps({'amount': '5000.00', 'payment_method': 'CARD'}),
            content_type='application/json',
        )
        self.assertEqual(resp_owner.status_code, 200)

        self.account1.refresh_from_db()
        self.assertEqual(self.account1.outstanding_balance, Decimal('30000.00'))

    def test_repay_form_encoded_payload(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})
        response = self.client.post(
            url,
            data={
                'amount': '4000.00',
                'payment_method': 'CARD',
                'reference': 'POS-TXN-4421',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.account1.refresh_from_db()
        self.assertEqual(self.account1.outstanding_balance, Decimal('36000.00'))

    def test_repay_validation_failures(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:credit_repay', kwargs={'account_id': self.account1.id})

        # Non-positive amount
        r1 = self.client.post(url, data=json.dumps({'amount': '0.00', 'payment_method': 'CASH'}), content_type='application/json')
        self.assertEqual(r1.status_code, 400)
        self.assertIn('amount', r1.json()['errors'])

        # Negative amount
        r2 = self.client.post(url, data=json.dumps({'amount': '-100.00', 'payment_method': 'CASH'}), content_type='application/json')
        self.assertEqual(r2.status_code, 400)
        self.assertIn('amount', r2.json()['errors'])

        # Exceeding outstanding balance (balance is 40,000)
        r3 = self.client.post(url, data=json.dumps({'amount': '50000.00', 'payment_method': 'CASH'}), content_type='application/json')
        self.assertEqual(r3.status_code, 400)
        self.assertIn('amount', r3.json()['errors'])

        # Invalid payment method (CREDIT)
        r4 = self.client.post(url, data=json.dumps({'amount': '1000.00', 'payment_method': 'CREDIT'}), content_type='application/json')
        self.assertEqual(r4.status_code, 400)
        self.assertIn('payment_method', r4.json()['errors'])

    def test_repay_nonexistent_account_404(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:credit_repay', kwargs={'account_id': '999999'})
        response = self.client.post(
            url,
            data=json.dumps({'amount': '1000.00', 'payment_method': 'CASH'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['success'])

    def test_repay_shorthand_url(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:repay_shorthand', kwargs={'account_id': self.account1.id})
        response = self.client.post(
            url,
            data=json.dumps({'amount': '2000.00', 'payment_method': 'CASH'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------------------------------
    # Account List Endpoint Tests
    # --------------------------------------------------------------------------

    def test_unauthenticated_list_denied_401(self):
        url = reverse('credits:credit_account_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 401)

    def test_management_can_list_all_credit_accounts(self):
        self.client.force_login(self.manager)
        url = reverse('credits:credit_account_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertGreaterEqual(data['summary']['total_accounts'], 2)
        account_ids = [acc['id'] for acc in data['accounts']]
        self.assertIn(self.account1.id, account_ids)
        self.assertIn(self.account2.id, account_ids)

    def test_customer_can_only_view_own_account_in_list(self):
        self.client.force_login(self.customer1)
        url = reverse('credits:credit_account_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['summary']['total_accounts'], 1)
        account_ids = [acc['id'] for acc in data['accounts']]
        self.assertIn(self.account1.id, account_ids)
        self.assertNotIn(self.account2.id, account_ids)

    def test_list_filters(self):
        self.client.force_login(self.manager)
        url = reverse('credits:credit_account_list')

        # Filter by customer name
        r_search = self.client.get(f'{url}?search=Grace', HTTP_ACCEPT='application/json')
        self.assertEqual(r_search.status_code, 200)
        self.assertEqual(len(r_search.json()['data']['accounts']), 1)
        self.assertEqual(r_search.json()['data']['accounts'][0]['customer']['id'], self.customer2.id)

        # Filter by has_balance=true
        r_bal = self.client.get(f'{url}?has_balance=true', HTTP_ACCEPT='application/json')
        self.assertEqual(r_bal.status_code, 200)
        self.assertEqual(len(r_bal.json()['data']['accounts']), 2)

    # --------------------------------------------------------------------------
    # Account Detail Endpoint Tests
    # --------------------------------------------------------------------------

    def test_unauthenticated_detail_denied_401(self):
        url = reverse('credits:credit_account_detail', kwargs={'account_id': self.account1.id})
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 401)

    def test_customer_can_view_own_detail_and_ledger(self):
        # Create a repayment transaction first
        self.account1.record_repayment(
            amount=Decimal('5000.00'),
            created_by=self.manager,
            reference='REC-HIST-1',
            notes='Sample repayment for history test',
        )

        self.client.force_login(self.customer1)
        url = reverse('credits:credit_account_detail', kwargs={'account_id': self.account1.id})
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        res_data = response.json()['data']
        self.assertEqual(res_data['account']['id'], self.account1.id)
        self.assertGreaterEqual(len(res_data['transactions']), 1)
        self.assertEqual(res_data['transactions'][0]['reference'], 'REC-HIST-1')

    def test_customer_cannot_view_another_customer_detail_403(self):
        self.client.force_login(self.customer1)
        # Attempt to access customer2's account
        url = reverse('credits:credit_account_detail', kwargs={'account_id': self.account2.id})
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_staff_can_view_any_customer_detail(self):
        self.client.force_login(self.cashier)
        url1 = reverse('credits:credit_account_detail', kwargs={'account_id': self.account1.id})
        r1 = self.client.get(url1, HTTP_ACCEPT='application/json')
        self.assertEqual(r1.status_code, 200)

        url2 = reverse('credits:credit_account_detail', kwargs={'account_id': self.account2.id})
        r2 = self.client.get(url2, HTTP_ACCEPT='application/json')
        self.assertEqual(r2.status_code, 200)

    def test_detail_nonexistent_account_404(self):
        self.client.force_login(self.cashier)
        url = reverse('credits:credit_account_detail', kwargs={'account_id': '999999'})
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 404)

    # --------------------------------------------------------------------------
    # Payment Page View Tests
    # --------------------------------------------------------------------------

    def test_credit_payment_page_staff_allowed_customer_denied(self):
        url = reverse('credits:credit_payment_page')

        # Cashier
        self.client.force_login(self.cashier)
        r_cashier = self.client.get(url)
        self.assertEqual(r_cashier.status_code, 200)

        # Customer
        self.client.force_login(self.customer1)
        r_cust = self.client.get(url)
        self.assertEqual(r_cust.status_code, 403)


class CreditProvisioningViewTests(TestCase):
    """Automated tests for Manager/Owner Customer Credit Provisioning Interface."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email='prov_owner@example.com',
            username='prov_owner',
            first_name='Amara',
            last_name='Owner',
            password='StrongPass123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='prov_manager@example.com',
            username='prov_manager',
            first_name='Ken',
            last_name='Manager',
            password='StrongPass123',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            email='prov_cashier@example.com',
            username='prov_cashier',
            first_name='Titi',
            last_name='Cashier',
            password='StrongPass123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='prov_customer@example.com',
            username='prov_customer',
            first_name='Ngozi',
            last_name='Eze',
            password='StrongPass123',
            role='CUSTOMER',
        )
        self.account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
            outstanding_balance=Decimal('10000.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )

    def test_manager_can_add_credit(self):
        """Confirm Manager/Owner can grant credit and balance increments correctly."""
        url = reverse('credits:add_customer_credit')

        # Test Manager provisioning
        self.client.force_login(self.manager)
        resp = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '25000.00',
                'transaction_type': 'TOP_UP',
                'notes': 'Management quarterly loyalty credit',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertTrue(json_data['success'])
        self.assertIn('Successfully added ₦25000.00 credit', json_data['message'])

        self.account.refresh_from_db()
        self.assertEqual(self.account.credit_limit, Decimal('75000.00'))
        self.assertEqual(self.account.get_available_credit(), Decimal('65000.00'))

        # Verify CreditTransaction created
        tx = CreditTransaction.objects.filter(credit_account=self.account).order_by('-created_at').first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('25000.00'))
        self.assertEqual(tx.transaction_type, CreditTransaction.TransactionType.CREDIT_ISSUED)
        self.assertEqual(tx.created_by, self.manager)

        # Test Owner can also provision credit
        self.client.force_login(self.owner)
        resp_owner = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '15000.00',
                'transaction_type': 'TOP_UP',
                'notes': 'Owner VIP credit adjustment',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_owner.status_code, 200)
        self.account.refresh_from_db()
        self.assertEqual(self.account.credit_limit, Decimal('90000.00'))
        self.assertEqual(self.account.get_available_credit(), Decimal('80000.00'))

    def test_cashier_cannot_add_credit(self):
        """Confirm Cashier role receives HTTP 403 Forbidden."""
        url = reverse('credits:add_customer_credit')
        self.client.force_login(self.cashier)

        # GET request blocked
        resp_get = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(resp_get.status_code, 403)

        # POST request blocked
        resp_post = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '10000.00',
                'notes': 'Cashier unauthorized credit attempt',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_post.status_code, 403)

        # Customer role blocked
        self.client.force_login(self.customer)
        resp_cust = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '10000.00',
                'notes': 'Customer self credit attempt',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_cust.status_code, 403)

        # Confirm account was unchanged
        self.account.refresh_from_db()
        self.assertEqual(self.account.credit_limit, Decimal('50000.00'))

    def test_invalid_credit_amount_rejected(self):
        """Confirm negative or zero amounts fail validation."""
        url = reverse('credits:add_customer_credit')
        self.client.force_login(self.manager)

        # Negative amount
        resp_neg = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '-5000.00',
                'notes': 'Negative test',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_neg.status_code, 400)
        self.assertFalse(resp_neg.json()['success'])
        self.assertIn('amount', resp_neg.json().get('errors', {}))

        # Zero amount
        resp_zero = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '0.00',
                'notes': 'Zero amount test',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_zero.status_code, 400)
        self.assertFalse(resp_zero.json()['success'])

        # Non-numeric amount
        resp_str = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': 'invalid_num',
                'notes': 'String test',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_str.status_code, 400)

        # Missing reason/note
        resp_no_note = self.client.post(
            url,
            data=json.dumps({
                'customer_id': self.customer.id,
                'amount': '5000.00',
                'notes': '',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_no_note.status_code, 400)
        self.assertIn('notes', resp_no_note.json().get('errors', {}))


class CreditPaymentFlowTests(TestCase):
    """Automated tests for paying with store credit."""

    def setUp(self):
        self.category = ProductCategory.objects.create(name='Credit Test Category', slug='credit-test-cat')
        self.product = Product.objects.create(
            name='Luxury Silk',
            slug='luxury-silk',
            sku='SILK-001',
            category=self.category,
            selling_price=Decimal('10000.00'),
            cost_price=Decimal('6000.00'),
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=20)

        self.owner = User.objects.create_user(
            email='owner_credit_flow@example.com',
            username='owner_credit_flow',
            password='Password123',
            role='OWNER',
        )
        self.cashier = User.objects.create_user(
            email='cashier_credit_flow@example.com',
            username='cashier_credit_flow',
            password='Password123',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            email='customer_credit_flow@example.com',
            username='customer_credit_flow',
            password='Password123',
            role='CUSTOMER',
            first_name='Chioma',
            last_name='Nnamdi',
        )
        self.credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('50000.00'),
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
                'items': [{'product_id': self.product.id, 'quantity': 2, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 200)
        sale_id = create_resp.json()['data']['sale']['id']

        complete_resp = self.client.post(
            f'/sales/{sale_id}/complete/',
            data=json.dumps({'notes': 'Credit sale completion'}),
            content_type='application/json',
        )
        self.assertEqual(complete_resp.status_code, 200)
        sale_data = complete_resp.json()['data']
        self.assertEqual(sale_data['status'], Sale.SaleStatus.COMPLETED)
        self.assertEqual(sale_data['payment_status'], Sale.PaymentStatus.COMPLETED)

        # Inventory decreases
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 18)

        # Debt increases
        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, Decimal('20000.00'))
        self.assertEqual(self.credit_account.current_balance, Decimal('20000.00'))
        self.assertEqual(self.credit_account.get_available_credit(), Decimal('30000.00'))

    def test_customer_cannot_exceed_credit_limit(self):
        """Rejects with 400 error and helpful message."""
        self.client.force_login(self.cashier)
        # Attempt to purchase 6 units * 10000 = 60000 > credit_limit of 50000
        create_resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'customer_id': self.customer.id,
                'payment_method': 'CREDIT',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 6, 'discount': '0.00'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 400)
        data = create_resp.json()
        self.assertFalse(data['success'])
        errors_str = str(data.get('errors') or data.get('message'))
        self.assertTrue('credit' in errors_str.lower() or 'limit' in errors_str.lower())

    def test_credit_transaction_audit_logged(self):
        """Confirms CreditTransaction record exists with correct amount and user."""
        self.client.force_login(self.cashier)
        create_resp = self.client.post(
            '/sales/',
            data=json.dumps({
                'customer_id': self.customer.id,
                'payment_method': 'CREDIT',
                'discount': '0.00',
                'items': [{'product_id': self.product.id, 'quantity': 1, 'discount': '0.00'}],
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
