from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.inventory.models import InventoryItem
from apps.payments.models import Payment
from apps.products.models import Product, ProductCategory
from apps.sales.models import Sale
from .models import CreditAccount, CreditTransaction


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
