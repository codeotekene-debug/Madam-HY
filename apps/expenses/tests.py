from decimal import Decimal
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.expenses.models import Expense
from .services import ExpenseService


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


class ExpenseServiceTests(TestCase):
    """Unit tests for ExpenseService business logic, permissions, and audit logging."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='exp_owner_svc',
            email='exp_owner_svc@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='exp_manager_svc',
            email='exp_manager_svc@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='exp_cashier_svc',
            email='exp_cashier_svc@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.staff_user = User.objects.create_user(
            username='exp_staff_svc',
            email='exp_staff_svc@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='exp_cust_svc',
            email='exp_cust_svc@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )

    def test_service_create_expense_success(self):
        expense = ExpenseService.create_expense(
            recorded_by=self.cashier,
            amount=Decimal('4500.00'),
            category='SUPPLIES',
            expense_date='2026-10-01',
            vendor='Stationery Hub',
            payment_method='CASH',
            description='A4 Paper and Pens',
            notes='For counter use',
        )

        self.assertEqual(expense.amount, Decimal('4500.00'))
        self.assertEqual(expense.category, Expense.Category.SUPPLIES)
        self.assertEqual(expense.status, Expense.Status.PENDING)
        self.assertEqual(expense.recorded_by, self.cashier)
        self.assertTrue(expense.expense_reference.startswith('EXP-'))

        # Verify audit log
        log = ActivityLog.objects.filter(
            actor=self.cashier,
            action_type=ActivityLog.ActionType.CREATED,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('amount'), '4500.00')

    def test_service_create_expense_validations(self):
        # Customer role cannot record expenses
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.create_expense(
                recorded_by=self.customer,
                amount=Decimal('100.00'),
                category='OTHER',
                expense_date='2026-10-01',
            )
        self.assertIn('recorded_by', ctx.exception.message_dict)

        # Zero amount
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.create_expense(
                recorded_by=self.cashier,
                amount=Decimal('0.00'),
                category='OTHER',
                expense_date='2026-10-01',
            )
        self.assertIn('amount', ctx.exception.message_dict)

        # Negative amount
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.create_expense(
                recorded_by=self.cashier,
                amount=Decimal('-50.00'),
                category='OTHER',
                expense_date='2026-10-01',
            )
        self.assertIn('amount', ctx.exception.message_dict)

        # Invalid category
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.create_expense(
                recorded_by=self.cashier,
                amount=Decimal('50.00'),
                category='INVALID_CAT',
                expense_date='2026-10-01',
            )
        self.assertIn('category', ctx.exception.message_dict)

    def test_service_approve_expense_success(self):
        expense = ExpenseService.create_expense(
            recorded_by=self.staff_user,
            amount=Decimal('12000.00'),
            category='UTILITIES',
            expense_date='2026-10-02',
            vendor='Electric Co',
            payment_method='BANK_TRANSFER',
        )

        approved = ExpenseService.approve_expense(expense=expense, approved_by=self.manager)

        self.assertEqual(approved.status, Expense.Status.APPROVED)
        self.assertEqual(approved.approved_by, self.manager)
        self.assertIsNotNone(approved.approved_at)

        log = ActivityLog.objects.filter(
            actor=self.manager,
            action_type=ActivityLog.ActionType.APPROVED,
        ).first()
        self.assertIsNotNone(log)

    def test_service_approve_expense_rbac_and_status_checks(self):
        expense = ExpenseService.create_expense(
            recorded_by=self.staff_user,
            amount=Decimal('3000.00'),
            category='TRANSPORT',
            expense_date='2026-10-03',
        )

        # Cashier cannot approve
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.approve_expense(expense=expense, approved_by=self.cashier)
        self.assertIn('approved_by', ctx.exception.message_dict)

        # Staff cannot approve
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.approve_expense(expense=expense, approved_by=self.staff_user)
        self.assertIn('approved_by', ctx.exception.message_dict)

        # Approve once
        ExpenseService.approve_expense(expense=expense, approved_by=self.owner)

        # Cannot approve already approved expense
        with self.assertRaises(ValidationError) as ctx:
            ExpenseService.approve_expense(expense=expense, approved_by=self.owner)
        self.assertIn('status', ctx.exception.message_dict)

    def test_service_reject_expense_success(self):
        expense = ExpenseService.create_expense(
            recorded_by=self.cashier,
            amount=Decimal('7000.00'),
            category='MARKETING',
            expense_date='2026-10-04',
        )

        rejected = ExpenseService.reject_expense(
            expense=expense,
            rejected_by=self.owner,
            reason='Unbudgeted expense',
        )

        self.assertEqual(rejected.status, Expense.Status.REJECTED)
        self.assertEqual(rejected.approved_by, self.owner)
        self.assertEqual(rejected.rejection_reason, 'Unbudgeted expense')

        log = ActivityLog.objects.filter(
            actor=self.owner,
            action_type=ActivityLog.ActionType.REJECTED,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.metadata.get('reason'), 'Unbudgeted expense')

    def test_cannot_modify_approved_expense(self):
        expense = ExpenseService.create_expense(
            recorded_by=self.cashier,
            amount=Decimal('5000.00'),
            category='RENT',
            expense_date='2026-10-05',
        )
        ExpenseService.approve_expense(expense=expense, approved_by=self.manager)

        # Attempt modifying amount of approved expense
        expense.amount = Decimal('6000.00')
        with self.assertRaises(ValidationError):
            expense.save()

    def test_expense_summary_aggregation(self):
        ExpenseService.create_expense(
            recorded_by=self.cashier,
            amount=Decimal('1000.00'),
            category='SUPPLIES',
            expense_date='2026-10-01',
        )
        e2 = ExpenseService.create_expense(
            recorded_by=self.cashier,
            amount=Decimal('2000.00'),
            category='SUPPLIES',
            expense_date='2026-10-02',
        )
        ExpenseService.approve_expense(e2, approved_by=self.owner)

        summary = ExpenseService.get_expense_summary(Expense.objects.all())
        self.assertEqual(Decimal(summary['total_expenses']), Decimal('3000.00'))
        self.assertEqual(Decimal(summary['approved_total']), Decimal('2000.00'))
        self.assertEqual(summary['pending_count'], 1)
        self.assertEqual(summary['top_category'], 'SUPPLIES')


class ExpenseHTTPViewsTests(TestCase):
    """Integration tests for Expense HTTP API, views, permissions, and approval workflow."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='exp_owner_http',
            email='exp_owner_http@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='exp_manager_http',
            email='exp_manager_http@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='exp_cashier_http',
            email='exp_cashier_http@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.staff_user = User.objects.create_user(
            username='exp_staff_http',
            email='exp_staff_http@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='exp_cust_http',
            email='exp_cust_http@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )

        self.exp1 = Expense.objects.create(
            expense_reference='EXP-HTTP-001',
            category=Expense.Category.RENT,
            description='Shop October Rent',
            amount=Decimal('50000.00'),
            expense_date='2026-10-01',
            vendor='Prime Realty',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            status=Expense.Status.APPROVED,
            recorded_by=self.owner,
            approved_by=self.owner,
            approved_at=timezone.now(),
        )
        self.exp2 = Expense.objects.create(
            expense_reference='EXP-HTTP-002',
            category=Expense.Category.SUPPLIES,
            description='Printer Paper & Cartridges',
            amount=Decimal('8500.00'),
            expense_date='2026-10-02',
            vendor='Office Depot',
            payment_method=Expense.PaymentMethod.CASH,
            status=Expense.Status.PENDING,
            recorded_by=self.cashier,
        )
        self.exp3 = Expense.objects.create(
            expense_reference='EXP-HTTP-003',
            category=Expense.Category.UTILITIES,
            description='Power Generator Fuel',
            amount=Decimal('15000.00'),
            expense_date='2026-10-03',
            vendor='Total Energies',
            payment_method=Expense.PaymentMethod.CARD,
            status=Expense.Status.PENDING,
            recorded_by=self.staff_user,
        )

    # --------------------------------------------------------------------------
    # List View Tests
    # --------------------------------------------------------------------------

    def test_unauthenticated_list_denied_401(self):
        url = reverse('expenses:expense_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 401)

    def test_customer_list_denied_403(self):
        self.client.force_login(self.customer)
        url = reverse('expenses:expense_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_cashier_and_staff_only_see_own_expenses_in_list(self):
        # Cashier
        self.client.force_login(self.cashier)
        url = reverse('expenses:expense_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        items = response.json()['data']['expenses']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['expense_reference'], 'EXP-HTTP-002')

        # Staff user
        self.client.force_login(self.staff_user)
        response_staff = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response_staff.status_code, 200)
        items_staff = response_staff.json()['data']['expenses']
        self.assertEqual(len(items_staff), 1)
        self.assertEqual(items_staff[0]['expense_reference'], 'EXP-HTTP-003')

    def test_manager_and_owner_see_all_expenses_in_list(self):
        self.client.force_login(self.manager)
        url = reverse('expenses:expense_list')
        response = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        items = response.json()['data']['expenses']
        self.assertGreaterEqual(len(items), 3)

    def test_list_filters_and_pagination(self):
        self.client.force_login(self.manager)
        url = reverse('expenses:expense_list')

        # Filter by category
        r_cat = self.client.get(f'{url}?category=RENT', HTTP_ACCEPT='application/json')
        self.assertEqual(r_cat.status_code, 200)
        self.assertEqual(len(r_cat.json()['data']['expenses']), 1)
        self.assertEqual(r_cat.json()['data']['expenses'][0]['category'], 'RENT')

        # Filter by status
        r_stat = self.client.get(f'{url}?status=PENDING', HTTP_ACCEPT='application/json')
        self.assertEqual(r_stat.status_code, 200)
        self.assertEqual(len(r_stat.json()['data']['expenses']), 2)

        # Filter by search
        r_search = self.client.get(f'{url}?search=Generator', HTTP_ACCEPT='application/json')
        self.assertEqual(r_search.status_code, 200)
        self.assertEqual(len(r_search.json()['data']['expenses']), 1)
        self.assertEqual(r_search.json()['data']['expenses'][0]['vendor'], 'Total Energies')

        # Pagination
        r_page = self.client.get(f'{url}?page=1&page_size=2', HTTP_ACCEPT='application/json')
        self.assertEqual(r_page.status_code, 200)
        self.assertEqual(len(r_page.json()['data']['expenses']), 2)
        self.assertEqual(r_page.json()['data']['pagination']['pages'], 2)

    # --------------------------------------------------------------------------
    # Create View Tests
    # --------------------------------------------------------------------------

    def test_create_expense_unauthenticated_denied_401(self):
        url = reverse('expenses:expense_create')
        response = self.client.post(
            url,
            data=json.dumps({
                'amount': '2500.00',
                'category': 'SUPPLIES',
                'expense_date': '2026-10-06',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_create_expense_customer_denied_403(self):
        self.client.force_login(self.customer)
        url = reverse('expenses:expense_create')
        response = self.client.post(
            url,
            data=json.dumps({
                'amount': '2500.00',
                'category': 'SUPPLIES',
                'expense_date': '2026-10-06',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_create_expense_staff_allowed_json_and_form(self):
        self.client.force_login(self.cashier)
        url = reverse('expenses:expense_create')

        # JSON submission
        response = self.client.post(
            url,
            data=json.dumps({
                'amount': '3200.00',
                'category': 'MAINTENANCE',
                'expense_date': '2026-10-06',
                'vendor': 'AC Technician',
                'payment_method': 'CASH',
                'description': 'AC servicing',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['data']['category'], 'MAINTENANCE')
        self.assertEqual(res_data['data']['status'], 'PENDING')
        self.assertEqual(res_data['data']['recorded_by']['id'], self.cashier.id)

        # Form-encoded submission
        r_form = self.client.post(
            url,
            data={
                'amount': '1500.00',
                'category': 'OTHER',
                'expense_date': '2026-10-06',
                'vendor': 'Local Shop',
                'payment_method': 'CASH',
            },
        )
        self.assertIn(r_form.status_code, (200, 201, 302))

    def test_create_expense_validations_400(self):
        self.client.force_login(self.cashier)
        url = reverse('expenses:expense_create')

        # Non-positive amount
        r1 = self.client.post(
            url,
            data=json.dumps({
                'amount': '0.00',
                'category': 'SUPPLIES',
                'expense_date': '2026-10-06',
            }),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 400)
        self.assertIn('amount', r1.json()['errors'])

        # Invalid category
        r2 = self.client.post(
            url,
            data=json.dumps({
                'amount': '100.00',
                'category': 'INVALID_CATEGORY',
                'expense_date': '2026-10-06',
            }),
            content_type='application/json',
        )
        self.assertEqual(r2.status_code, 400)
        self.assertIn('category', r2.json()['errors'])

    # --------------------------------------------------------------------------
    # Detail View Tests
    # --------------------------------------------------------------------------

    def test_detail_view_permissions_and_customer_isolation(self):
        url = reverse('expenses:expense_detail', kwargs={'id': self.exp2.uuid})

        # Unauthenticated
        r_unauth = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(r_unauth.status_code, 401)

        # Customer denied
        self.client.force_login(self.customer)
        r_cust = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(r_cust.status_code, 403)

        # Staff user who did NOT record exp2
        self.client.force_login(self.staff_user)
        r_staff = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(r_staff.status_code, 403)

        # Cashier who DID record exp2
        self.client.force_login(self.cashier)
        r_cashier = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(r_cashier.status_code, 200)
        self.assertEqual(r_cashier.json()['data']['expense_reference'], 'EXP-HTTP-002')

        # Manager can view any expense
        self.client.force_login(self.manager)
        r_mgr = self.client.get(url, HTTP_ACCEPT='application/json')
        self.assertEqual(r_mgr.status_code, 200)

    def test_detail_view_lookup_by_uuid_int_and_ref(self):
        self.client.force_login(self.manager)

        # Lookup by UUID
        url_uuid = reverse('expenses:expense_detail', kwargs={'id': self.exp1.uuid})
        self.assertEqual(self.client.get(url_uuid, HTTP_ACCEPT='application/json').status_code, 200)

        # Lookup by integer PK
        url_pk = reverse('expenses:expense_detail', kwargs={'id': self.exp1.id})
        self.assertEqual(self.client.get(url_pk, HTTP_ACCEPT='application/json').status_code, 200)

        # Lookup by reference string
        url_ref = reverse('expenses:expense_detail', kwargs={'id': self.exp1.expense_reference})
        self.assertEqual(self.client.get(url_ref, HTTP_ACCEPT='application/json').status_code, 200)

    def test_detail_view_nonexistent_404(self):
        self.client.force_login(self.manager)
        url = reverse('expenses:expense_detail', kwargs={'id': '999999'})
        self.assertEqual(self.client.get(url, HTTP_ACCEPT='application/json').status_code, 404)

    # --------------------------------------------------------------------------
    # Approval & Rejection Action Tests
    # --------------------------------------------------------------------------

    def test_approve_expense_rbac(self):
        url = reverse('expenses:expense_approve', kwargs={'id': self.exp2.uuid})

        # Unauthenticated
        self.assertEqual(self.client.post(url).status_code, 401)

        # Customer denied
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url).status_code, 403)

        # Cashier denied
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(url).status_code, 403)

        # Staff denied
        self.client.force_login(self.staff_user)
        self.assertEqual(self.client.post(url).status_code, 403)

        # Manager allowed
        self.client.force_login(self.manager)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['status'], 'APPROVED')

        self.exp2.refresh_from_db()
        self.assertEqual(self.exp2.status, Expense.Status.APPROVED)
        self.assertEqual(self.exp2.approved_by, self.manager)

    def test_approve_already_approved_expense_400(self):
        self.client.force_login(self.manager)
        # exp1 is already approved in setUp
        url = reverse('expenses:expense_approve', kwargs={'id': self.exp1.uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_reject_expense_rbac(self):
        url = reverse('expenses:expense_reject', kwargs={'id': self.exp3.uuid})

        # Cashier denied
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(url).status_code, 403)

        # Owner allowed
        self.client.force_login(self.owner)
        resp = self.client.post(
            url,
            data=json.dumps({'reason': 'Over budgeted threshold'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['status'], 'REJECTED')
        self.assertEqual(resp.json()['data']['rejection_reason'], 'Over budgeted threshold')

        self.exp3.refresh_from_db()
        self.assertEqual(self.exp3.status, Expense.Status.REJECTED)
        self.assertEqual(self.exp3.approved_by, self.owner)

    def test_reject_already_approved_expense_400(self):
        self.client.force_login(self.owner)
        url = reverse('expenses:expense_reject', kwargs={'id': self.exp1.uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
