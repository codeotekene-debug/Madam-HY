from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.test import TestCase

from apps.accounts.models import User
from apps.expenses.models import Expense


class ExpenseModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='expense_owner',
            email='expense_owner@example.com',
            password='StrongPass123!',
            first_name='Expense',
            last_name='Owner',
            role='OWNER',
        )

    def test_expense_creation(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1001',
            category=Expense.Category.RENT,
            description='Monthly shop rent',
            amount=Decimal('2500.00'),
            expense_date='2026-08-01',
            vendor='City Property Ltd',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            payment_reference='BANK-REF-001',
            recorded_by=self.user,
            notes='August rent invoice',
        )

        self.assertEqual(expense.expense_reference, 'EXP-1001')
        self.assertEqual(expense.category, Expense.Category.RENT)
        self.assertEqual(expense.amount, Decimal('2500.00'))
        self.assertEqual(expense.vendor, 'City Property Ltd')
        self.assertEqual(expense.recorded_by, self.user)

    def test_unique_expense_reference(self):
        Expense.objects.create(
            expense_reference='EXP-UNIQUE-1',
            category=Expense.Category.UTILITIES,
            description='Electricity',
            amount=Decimal('150.25'),
            expense_date='2026-08-02',
            vendor='Metro Power',
            payment_method=Expense.PaymentMethod.CARD,
            recorded_by=self.user,
        )

        with self.assertRaises(ValidationError):
            Expense.objects.create(
                expense_reference='EXP-UNIQUE-1',
                category=Expense.Category.SALARIES,
                description='Duplicate reference',
                amount=Decimal('1000.00'),
                expense_date='2026-08-03',
                vendor='Duplicate Vendor',
                payment_method=Expense.PaymentMethod.CASH,
                recorded_by=self.user,
            )

    def test_category_choices(self):
        self.assertIn((Expense.Category.RENT, 'Rent'), Expense.Category.choices)
        self.assertIn((Expense.Category.UTILITIES, 'Utilities'), Expense.Category.choices)
        self.assertIn((Expense.Category.SUPPLIES, 'Supplies'), Expense.Category.choices)
        self.assertIn((Expense.Category.MAINTENANCE, 'Maintenance'), Expense.Category.choices)
        self.assertIn((Expense.Category.TRANSPORT, 'Transport'), Expense.Category.choices)
        self.assertIn((Expense.Category.SALARIES, 'Salaries'), Expense.Category.choices)
        self.assertIn((Expense.Category.MARKETING, 'Marketing'), Expense.Category.choices)
        self.assertIn((Expense.Category.OTHER, 'Other'), Expense.Category.choices)

    def test_payment_method_choices(self):
        self.assertIn((Expense.PaymentMethod.CASH, 'Cash'), Expense.PaymentMethod.choices)
        self.assertIn((Expense.PaymentMethod.BANK_TRANSFER, 'Bank Transfer'), Expense.PaymentMethod.choices)
        self.assertIn((Expense.PaymentMethod.CARD, 'Card'), Expense.PaymentMethod.choices)
        self.assertIn((Expense.PaymentMethod.OTHER, 'Other'), Expense.PaymentMethod.choices)

    def test_positive_amount(self):
        expense = Expense(
            expense_reference='EXP-1002',
            category=Expense.Category.OTHER,
            description='Office snacks',
            amount=Decimal('45.00'),
            expense_date='2026-08-04',
            vendor='Corner Mart',
            payment_method=Expense.PaymentMethod.CASH,
            recorded_by=self.user,
        )
        expense.full_clean()
        self.assertEqual(expense.amount, Decimal('45.00'))

    def test_zero_amount_rejected(self):
        expense = Expense(
            expense_reference='EXP-1003',
            category=Expense.Category.SUPPLIES,
            description='Zero amount',
            amount=Decimal('0.00'),
            expense_date='2026-08-05',
            vendor='No Vendor',
            payment_method=Expense.PaymentMethod.CASH,
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_negative_amount_rejected(self):
        expense = Expense(
            expense_reference='EXP-1004',
            category=Expense.Category.TRANSPORT,
            description='Negative value',
            amount=Decimal('-10.50'),
            expense_date='2026-08-06',
            vendor='Fuel Vendor',
            payment_method=Expense.PaymentMethod.CARD,
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_expense_date_required(self):
        expense = Expense(
            expense_reference='EXP-1005',
            category=Expense.Category.MAINTENANCE,
            description='Repair',
            amount=Decimal('200.00'),
            expense_date=None,
            vendor='Workshop',
            payment_method=Expense.PaymentMethod.CARD,
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            expense.full_clean()

    def test_vendor_payee(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1006',
            category=Expense.Category.MARKETING,
            description='Campaign ad',
            amount=Decimal('900.00'),
            expense_date='2026-08-07',
            vendor='Digital Reach',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            payment_reference='AD-123',
            recorded_by=self.user,
        )
        self.assertEqual(expense.vendor, 'Digital Reach')
        self.assertEqual(expense.payment_reference, 'AD-123')

    def test_recorded_by_relationship(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1007',
            category=Expense.Category.RENT,
            description='Lease',
            amount=Decimal('6000.00'),
            expense_date='2026-08-08',
            vendor='Property Group',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            recorded_by=self.user,
        )
        self.assertEqual(expense.recorded_by_id, self.user.pk)
        self.assertEqual(expense.recorded_by.email, self.user.email)

    def test_decimal_precision(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1008',
            category=Expense.Category.UTILITIES,
            description='Power bill',
            amount=Decimal('1234.56'),
            expense_date='2026-08-09',
            vendor='Power Company',
            payment_method=Expense.PaymentMethod.CARD,
            recorded_by=self.user,
        )
        self.assertEqual(expense.amount, Decimal('1234.56'))
        self.assertEqual(expense._meta.get_field('amount').max_digits, 12)
        self.assertEqual(expense._meta.get_field('amount').decimal_places, 2)

    def test_historical_record_protection(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1009',
            category=Expense.Category.OTHER,
            description='Office repair',
            amount=Decimal('180.00'),
            expense_date='2026-08-10',
            vendor='Repairs Co',
            payment_method=Expense.PaymentMethod.OTHER,
            recorded_by=self.user,
        )

        with self.assertRaises(ValidationError):
            expense.delete()

    def test_database_constraints(self):
        constraints = Expense._meta.constraints
        constraint_names = {constraint.name for constraint in constraints}
        self.assertIn('expense_amount_positive', constraint_names)
        self.assertIn('expense_reference_unique', constraint_names)

    def test_django_system_checks(self):
        self.assertEqual(Expense.check(), [])

    def test_expenses_do_not_modify_inventory(self):
        expense_fields = [field.name for field in Expense._meta.get_fields()]
        self.assertNotIn('inventory_item', expense_fields)
        self.assertNotIn('stock_movement', expense_fields)

    def test_expenses_do_not_modify_sales(self):
        expense_fields = [field.name for field in Expense._meta.get_fields()]
        self.assertNotIn('sale', expense_fields)
        self.assertNotIn('sale_item', expense_fields)

    def test_expenses_do_not_modify_payments(self):
        expense_fields = [field.name for field in Expense._meta.get_fields()]
        self.assertNotIn('payment', expense_fields)
        self.assertNotIn('sale', expense_fields)
        self.assertNotIn('order', expense_fields)

    def test_expenses_do_not_modify_credits(self):
        expense_fields = [field.name for field in Expense._meta.get_fields()]
        self.assertNotIn('credit_account', expense_fields)
        self.assertNotIn('credit_transaction', expense_fields)
