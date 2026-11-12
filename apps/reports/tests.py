from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.credits.models import CreditAccount, CreditTransaction
from apps.expenses.models import Expense
from apps.inventory.models import InventoryItem
from apps.products.models import Product, ProductCategory
from apps.reports.services import (
    credit_summary,
    expense_report,
    get_date_range,
    growth_report,
    inventory_summary,
    profit_report,
    sales_report,
)
from apps.sales.models import Sale, SaleItem
from django.urls import reverse


class ReportsServiceTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.customer = User.objects.create_user(
            username='report_customer',
            email='report_customer@example.com',
            password='StrongPass123!',
            first_name='Report',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.cashier = User.objects.create_user(
            username='report_cashier',
            email='report_cashier@example.com',
            password='StrongPass123!',
            first_name='Report',
            last_name='Cashier',
            role='CASHIER',
        )
        self.manager = User.objects.create_user(
            username='report_manager',
            email='report_manager@example.com',
            password='StrongPass123!',
            first_name='Report',
            last_name='Manager',
            role='MANAGER',
        )

        self.category = ProductCategory.objects.create(
            name='Food',
            slug='food',
            description='Food products',
        )
        self.product_a = Product.objects.create(
            category=self.category,
            name='Rice 5kg',
            slug='rice-5kg',
            sku='RICE-5KG-001',
            description='Household rice',
            selling_price=Decimal('100.00'),
            cost_price=Decimal('50.00'),
            reorder_level=5,
        )
        self.product_b = Product.objects.create(
            category=self.category,
            name='Beans 5kg',
            slug='beans-5kg',
            sku='BEANS-5KG-001',
            description='Beans',
            selling_price=Decimal('200.00'),
            cost_price=Decimal('80.00'),
            reorder_level=3,
        )

        self.inventory_a = InventoryItem.objects.create(product=self.product_a, quantity=20)
        self.inventory_b = InventoryItem.objects.create(product=self.product_b, quantity=0)

        self.sale_cash = Sale.objects.create(
            sale_number='S-1001',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.COMPLETED,
            payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('300.00'),
            total=Decimal('300.00'),
            amount_received=Decimal('300.00'),
            change_amount=Decimal('0.00'),
            notes='Cash sale',
        )
        SaleItem.objects.create(
            sale=self.sale_cash,
            product=self.product_a,
            quantity=2,
            unit_price=Decimal('100.00'),
            product_name_snapshot=self.product_a.name,
            sku_snapshot=self.product_a.sku,
        )
        SaleItem.objects.create(
            sale=self.sale_cash,
            product=self.product_b,
            quantity=1,
            unit_price=Decimal('200.00'),
            product_name_snapshot=self.product_b.name,
            sku_snapshot=self.product_b.sku,
        )

        self.sale_card = Sale.objects.create(
            sale_number='S-1002',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.COMPLETED,
            payment_method=Sale.PaymentMethod.CARD,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            amount_received=Decimal('200.00'),
            change_amount=Decimal('0.00'),
            notes='Card sale',
        )
        SaleItem.objects.create(
            sale=self.sale_card,
            product=self.product_b,
            quantity=1,
            unit_price=Decimal('200.00'),
            product_name_snapshot=self.product_b.name,
            sku_snapshot=self.product_b.sku,
        )

        self.draft_sale = Sale.objects.create(
            sale_number='S-1003',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.DRAFT,
            payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.PENDING,
            subtotal=Decimal('999.00'),
            total=Decimal('999.00'),
        )

        self.expense_rent = Expense.objects.create(
            expense_reference='EXP-1001',
            category=Expense.Category.RENT,
            description='Shop rent',
            amount=Decimal('150.00'),
            expense_date=self.today,
            vendor='City Property Ltd',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            payment_reference='BANK-1001',
            status=Expense.Status.APPROVED,
            recorded_by=self.manager,
        )
        self.expense_utilities = Expense.objects.create(
            expense_reference='EXP-1002',
            category=Expense.Category.UTILITIES,
            description='Power bill',
            amount=Decimal('50.00'),
            expense_date=self.today,
            vendor='Metro Power',
            payment_method=Expense.PaymentMethod.CARD,
            payment_reference='CARD-1002',
            status=Expense.Status.APPROVED,
            recorded_by=self.manager,
        )

        self.credit_account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal('1000.00'),
            outstanding_balance=Decimal('250.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.manager,
            next_due_date=self.today + timedelta(days=10),
        )
        CreditTransaction.objects.create(
            credit_account=self.credit_account,
            transaction_type=CreditTransaction.TransactionType.REPAYMENT,
            amount=Decimal('50.00'),
            previous_balance=Decimal('250.00'),
            new_balance=Decimal('200.00'),
            reference='CRD-REP-1',
            created_by=self.manager,
        )

    def test_empty_reporting_period(self):
        start_date = self.today + timedelta(days=30)
        end_date = start_date + timedelta(days=7)
        sale_result = sales_report(period='custom', start_date=start_date, end_date=end_date)
        expense_result = expense_report(period='custom', start_date=start_date, end_date=end_date)

        self.assertEqual(sale_result['total_sales'], Decimal('0.00'))
        self.assertEqual(sale_result['sales_count'], 0)
        self.assertEqual(expense_result['total_expenses'], Decimal('0.00'))
        self.assertEqual(expense_result['expense_count'], 0)

    def test_date_range_filtering(self):
        period = get_date_range(period='today')
        self.assertEqual(period['start_date'], self.today)
        self.assertEqual(period['end_date'], self.today)

        quarter = get_date_range(period='this_quarter')
        quarter_start_month = ((timezone.localdate().month - 1) // 3) * 3 + 1
        self.assertEqual(quarter['start_date'], timezone.localdate().replace(month=quarter_start_month, day=1))
        self.assertEqual(quarter['end_date'].month, quarter_start_month + 2)

    def test_quarter_growth_report_uses_previous_calendar_quarter(self):
        result = growth_report(period='this_quarter')
        current_start = result['start_date']
        self.assertEqual(current_start.month, ((timezone.localdate().month - 1) // 3) * 3 + 1)
        self.assertEqual(result['previous_end_date'] + timedelta(days=1), current_start)
        self.assertEqual(result['previous_start_date'].month, ((current_start.month - 4) % 12) // 3 * 3 + 1)

    def test_sales_total_and_count(self):
        result = sales_report(period='today')
        self.assertEqual(result['total_sales'], Decimal('500.00'))
        self.assertEqual(result['sales_count'], 2)

    def test_completed_sales_only(self):
        result = sales_report(period='today')
        self.assertEqual(result['sales_count'], 2)
        self.assertEqual(result['total_sales'], Decimal('500.00'))
        self.assertNotEqual(result['total_sales'], Decimal('999.00'))

    def test_average_sale(self):
        result = sales_report(period='today')
        self.assertEqual(result['average_sale'], Decimal('250.00'))

    def test_sales_by_payment_method(self):
        result = sales_report(period='today')
        methods = {item['payment_method']: item['total_sales'] for item in result['sales_by_payment_method']}
        self.assertEqual(methods['CASH'], Decimal('300.00'))
        self.assertEqual(methods['CARD'], Decimal('200.00'))

    def test_sales_by_cashier(self):
        result = sales_report(period='today')
        cashiers = {item['cashier_name']: item['total_sales'] for item in result['sales_by_cashier']}
        self.assertEqual(cashiers['Report Cashier'], Decimal('500.00'))

    def test_top_selling_products(self):
        result = sales_report(period='today')
        products = {item['product_name']: item['total_quantity'] for item in result['top_selling_products']}
        self.assertEqual(products['Rice 5kg'], 2)
        self.assertEqual(products['Beans 5kg'], 2)

    def test_sales_by_category(self):
        result = sales_report(period='today')
        categories = {item['category']: item['total_sales'] for item in result['sales_by_category']}
        self.assertEqual(categories['Food'], Decimal('600.00'))

    def test_expense_total_and_category_breakdown(self):
        result = expense_report(period='today')
        self.assertEqual(result['total_expenses'], Decimal('200.00'))
        self.assertEqual(result['expense_count'], 2)
        categories = {item['category']: item['total_expenses'] for item in result['expenses_by_category']}
        self.assertEqual(categories['RENT'], Decimal('150.00'))
        self.assertEqual(categories['UTILITIES'], Decimal('50.00'))

    def test_expenses_by_payment_method(self):
        result = expense_report(period='today')
        payment_methods = {item['payment_method']: item['total_expenses'] for item in result['expenses_by_payment_method']}
        self.assertEqual(payment_methods['BANK_TRANSFER'], Decimal('150.00'))
        self.assertEqual(payment_methods['CARD'], Decimal('50.00'))

    def test_profit_revenue_cost_and_margin(self):
        result = profit_report(period='today')
        self.assertEqual(result['revenue'], Decimal('500.00'))
        self.assertEqual(result['cost_of_goods_sold'], Decimal('260.00'))
        self.assertEqual(result['gross_profit'], Decimal('240.00'))
        self.assertEqual(result['expenses'], Decimal('200.00'))
        self.assertEqual(result['net_profit'], Decimal('40.00'))
        self.assertEqual(result['profit_margin'], Decimal('8.00'))

    def test_growth_report(self):
        result = growth_report(period='today')
        self.assertEqual(result['current_period_sales'], Decimal('500.00'))
        self.assertEqual(result['previous_period_sales'], Decimal('0.00'))
        self.assertEqual(result['sales_growth_percentage'], Decimal('100.00'))
        self.assertEqual(result['current_period_expenses'], Decimal('200.00'))
        self.assertEqual(result['previous_period_expenses'], Decimal('0.00'))
        self.assertEqual(result['expense_growth_percentage'], Decimal('100.00'))
        self.assertEqual(result['current_period_profit'], Decimal('40.00'))
        self.assertEqual(result['previous_period_profit'], Decimal('0.00'))
        self.assertEqual(result['profit_growth_percentage'], Decimal('100.00'))

    def test_zero_previous_period_handling(self):
        result = growth_report(period='custom', start_date=self.today, end_date=self.today)
        self.assertEqual(result['sales_growth_percentage'], Decimal('100.00'))
        self.assertEqual(result['expense_growth_percentage'], Decimal('100.00'))
        self.assertEqual(result['profit_growth_percentage'], Decimal('100.00'))

    def test_inventory_summary(self):
        result = inventory_summary()
        self.assertEqual(result['total_products'], 2)
        self.assertEqual(result['products_in_stock'], 1)
        self.assertEqual(result['low_stock_products'], 1)
        self.assertEqual(result['out_of_stock_products'], 1)
        self.assertEqual(result['total_inventory_quantity'], 20)
        self.assertEqual(result['inventory_value'], Decimal('2000.00'))

    def test_credit_summary(self):
        result = credit_summary(period='today')
        self.assertEqual(result['total_credit_limit'], Decimal('1000.00'))
        self.assertEqual(result['total_outstanding_credit'], Decimal('250.00'))
        self.assertEqual(result['available_credit'], Decimal('750.00'))
        self.assertEqual(result['active_credit_accounts'], 1)
        self.assertEqual(result['overdue_credit_accounts'], 0)
        self.assertEqual(result['repayments_during_period'], Decimal('50.00'))

    def test_no_mutation_of_source_models(self):
        sale_total_before = Sale.objects.get(pk=self.sale_cash.pk).total
        expense_total_before = Expense.objects.get(pk=self.expense_rent.pk).amount
        inventory_before = InventoryItem.objects.get(pk=self.inventory_b.pk).quantity
        credit_before = CreditAccount.objects.get(pk=self.credit_account.pk).outstanding_balance

        sales_report(period='today')
        expense_report(period='today')
        inventory_summary()
        credit_summary(period='today')

        self.assertEqual(Sale.objects.get(pk=self.sale_cash.pk).total, sale_total_before)
        self.assertEqual(Expense.objects.get(pk=self.expense_rent.pk).amount, expense_total_before)
        self.assertEqual(InventoryItem.objects.get(pk=self.inventory_b.pk).quantity, inventory_before)
        self.assertEqual(CreditAccount.objects.get(pk=self.credit_account.pk).outstanding_balance, credit_before)

    def test_decimal_precision(self):
        result = sales_report(period='today')
        self.assertEqual(result['average_sale'], Decimal('250.00'))
        self.assertEqual(result['total_sales'], Decimal('500.00'))

    def test_unapproved_expenses_excluded_from_profit_and_expense_reports(self):
        # Create a pending expense and a rejected expense
        Expense.objects.create(
            expense_reference='EXP-PENDING-01',
            category=Expense.Category.MARKETING,
            description='Pending flyer ad',
            vendor='Marketing Co',
            amount=Decimal('500.00'),
            expense_date=self.today,
            status=Expense.Status.PENDING,
            recorded_by=self.manager,
        )
        Expense.objects.create(
            expense_reference='EXP-REJECTED-01',
            category=Expense.Category.TRANSPORT,
            description='Rejected taxi ride',
            vendor='City Taxi',
            amount=Decimal('300.00'),
            expense_date=self.today,
            status=Expense.Status.REJECTED,
            recorded_by=self.manager,
        )
        # Approved expense report should still only be 200.00 (self.expense_rent + self.expense_utilities)
        exp_res = expense_report(period='today', status=Expense.Status.APPROVED)
        self.assertEqual(exp_res['total_expenses'], Decimal('200.00'))
        self.assertEqual(exp_res['expense_count'], 2)

        # Profit report should only deduct approved expenses
        profit_res = profit_report(period='today')
        self.assertEqual(profit_res['expenses'], Decimal('200.00'))
        self.assertEqual(profit_res['net_profit'], Decimal('40.00'))

    def test_django_system_checks(self):
        call_command('check')


class ReportsHTTPViewsTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.owner = User.objects.create_user(
            username='rep_owner',
            email='rep_owner@example.com',
            password='OwnerPass123!',
            first_name='Shop',
            last_name='Owner',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='rep_manager',
            email='rep_manager@example.com',
            password='ManagerPass123!',
            first_name='Store',
            last_name='Manager',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='rep_cashier',
            email='rep_cashier@example.com',
            password='CashierPass123!',
            first_name='Front',
            last_name='Cashier',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            username='rep_staff',
            email='rep_staff@example.com',
            password='StaffPass123!',
            first_name='Floor',
            last_name='Staff',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='rep_customer',
            email='rep_customer@example.com',
            password='CustomerPass123!',
            first_name='Client',
            last_name='Customer',
            role='CUSTOMER',
        )

        self.category = ProductCategory.objects.create(
            name='Groceries',
            slug='groceries',
            description='Everyday groceries',
        )
        self.product_1 = Product.objects.create(
            category=self.category,
            name='Sugar 1kg',
            slug='sugar-1kg',
            sku='SUG-1KG',
            selling_price=Decimal('50.00'),
            cost_price=Decimal('30.00'),
            reorder_level=10,
        )
        self.product_2 = Product.objects.create(
            category=self.category,
            name='Milk 1L',
            slug='milk-1l',
            sku='MLK-1L',
            selling_price=Decimal('100.00'),
            cost_price=Decimal('60.00'),
            reorder_level=5,
        )

        InventoryItem.objects.create(product=self.product_1, quantity=50)
        InventoryItem.objects.create(product=self.product_2, quantity=2)  # Low stock

        # Completed sale: 2x Sugar (100) + 1x Milk (100) = 200.00. COGS = 2*30 + 1*60 = 120.00. Gross = 80.00
        self.sale_1 = Sale.objects.create(
            sale_number='S-REP-01',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.COMPLETED,
            payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
            amount_received=Decimal('200.00'),
            change_amount=Decimal('0.00'),
        )
        SaleItem.objects.create(
            sale=self.sale_1,
            product=self.product_1,
            quantity=2,
            unit_price=Decimal('50.00'),
            product_name_snapshot=self.product_1.name,
            sku_snapshot=self.product_1.sku,
        )
        SaleItem.objects.create(
            sale=self.sale_1,
            product=self.product_2,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot=self.product_2.name,
            sku_snapshot=self.product_2.sku,
        )

        # Another completed sale: 1x Milk = 100.00. Payment method: CARD. COGS = 60. Gross = 40
        self.sale_2 = Sale.objects.create(
            sale_number='S-REP-02',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.COMPLETED,
            payment_method=Sale.PaymentMethod.CARD,
            payment_status=Sale.PaymentStatus.COMPLETED,
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
            amount_received=Decimal('100.00'),
            change_amount=Decimal('0.00'),
        )
        SaleItem.objects.create(
            sale=self.sale_2,
            product=self.product_2,
            quantity=1,
            unit_price=Decimal('100.00'),
            product_name_snapshot=self.product_2.name,
            sku_snapshot=self.product_2.sku,
        )

        # Draft sale (must be excluded from reporting)
        self.draft_sale = Sale.objects.create(
            sale_number='S-REP-DRAFT',
            customer=self.customer,
            cashier=self.cashier,
            status=Sale.SaleStatus.DRAFT,
            payment_method=Sale.PaymentMethod.CASH,
            payment_status=Sale.PaymentStatus.PENDING,
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
        )

        # Approved Expense: 30.00
        self.expense_appr = Expense.objects.create(
            expense_reference='EXP-APP-01',
            category=Expense.Category.UTILITIES,
            description='Internet bill',
            amount=Decimal('30.00'),
            expense_date=self.today,
            vendor='Speedy ISP',
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            status=Expense.Status.APPROVED,
            recorded_by=self.manager,
        )

        # Pending Expense (must be excluded from approved reports): 70.00
        self.expense_pend = Expense.objects.create(
            expense_reference='EXP-PND-01',
            category=Expense.Category.MARKETING,
            description='Ad campaign',
            amount=Decimal('70.00'),
            expense_date=self.today,
            vendor='Online Ads Co',
            payment_method=Expense.PaymentMethod.CARD,
            status=Expense.Status.PENDING,
            recorded_by=self.cashier,
        )

    # --------------------------------------------------------------------------
    # RBAC Tests
    # --------------------------------------------------------------------------

    def test_rbac_owner_and_manager_allowed(self):
        urls = [
            reverse('reports:reports_dashboard'),
            reverse('reports:sales_report'),
            reverse('reports:expense_report'),
            reverse('reports:profit_report'),
            reverse('reports:growth_report'),
        ]
        for role_user in (self.owner, self.manager):
            self.client.force_login(role_user)
            for url in urls:
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200, f'User {role_user.username} should access {url}')
                json_resp = self.client.get(url + '?format=json')
                self.assertEqual(json_resp.status_code, 200)
                self.assertTrue(json_resp.json()['success'])

    def test_rbac_cashier_forbidden(self):
        self.client.force_login(self.cashier)
        urls = [
            reverse('reports:reports_dashboard'),
            reverse('reports:sales_report'),
            reverse('reports:expense_report'),
            reverse('reports:profit_report'),
            reverse('reports:growth_report'),
        ]
        for url in urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403)
            self.assertFalse(resp.json()['success'])

    def test_rbac_staff_forbidden(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('reports:reports_dashboard'))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()['success'])

    def test_rbac_customer_forbidden(self):
        self.client.force_login(self.customer)
        resp = self.client.get(reverse('reports:sales_report'))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()['success'])

    def test_unauthenticated_json_returns_401(self):
        resp = self.client.get(reverse('reports:reports_dashboard') + '?format=json')
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()['success'])

    def test_unauthenticated_html_redirects_to_login(self):
        resp = self.client.get(reverse('reports:reports_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp.url)

    # --------------------------------------------------------------------------
    # Main Reports Dashboard Tests
    # --------------------------------------------------------------------------

    def test_reports_dashboard_html_view(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:reports_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/reports.html')
        self.assertIn('overview_data', resp.context)
        overview = resp.context['overview_data']
        self.assertEqual(overview['today_revenue'], Decimal('300.00'))
        self.assertEqual(overview['transactions'], 2)
        self.assertEqual(overview['low_stock_products'], 1)
        chart_points = resp.context['revenue_chart']
        self.assertTrue(chart_points)
        self.assertEqual(sum((point['revenue'] for point in chart_points), Decimal('0.00')), overview['total_sales'])
        self.assertNotContains(resp, 'style="--value: 42%"')

    def test_reports_dashboard_quarter_filter_and_chart_empty_state_data(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('reports:reports_dashboard') + '?period=this_quarter')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['period'], 'this_quarter')
        self.assertTrue(response.context['revenue_chart'])

    def test_reports_dashboard_json_view(self):
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('reports:reports_dashboard'), HTTP_ACCEPT='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        overview = data['data']['overview']
        self.assertEqual(overview['today_revenue'], '300.00')
        self.assertEqual(overview['low_stock_products'], 1)
        self.assertIn('sales', data['data'])
        self.assertIn('expenses', data['data'])
        self.assertIn('profit', data['data'])

    # --------------------------------------------------------------------------
    # Sales Report Tests
    # --------------------------------------------------------------------------

    def test_sales_report_html_and_json(self):
        self.client.force_login(self.manager)
        # HTML
        resp = self.client.get(reverse('reports:sales_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/sales_report.html')
        self.assertIn('sales_data', resp.context)
        self.assertEqual(resp.context['sales_data']['total_sales'], Decimal('300.00'))
        self.assertEqual(resp.context['sales_data']['sales_count'], 2)

        # JSON
        json_resp = self.client.get(reverse('reports:sales_report') + '?format=json')
        self.assertEqual(json_resp.status_code, 200)
        data = json_resp.json()['data']
        self.assertEqual(data['total_sales'], '300.00')
        self.assertEqual(data['sales_count'], 2)

    def test_sales_report_filter_by_period(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:sales_report') + '?period=today&format=json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['total_sales'], '300.00')

    def test_sales_report_custom_date_range(self):
        self.client.force_login(self.manager)
        start = str(self.today)
        end = str(self.today)
        resp = self.client.get(f"{reverse('reports:sales_report')}?period=custom&start_date={start}&end_date={end}&format=json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['total_sales'], '300.00')

    def test_sales_report_payment_method_filter(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:sales_report') + '?payment_method=CASH&format=json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('filtered_payment_methods', data)
        self.assertEqual(len(data['filtered_payment_methods']), 1)
        self.assertEqual(data['filtered_payment_methods'][0]['payment_method'], 'CASH')
        self.assertEqual(data['filtered_payment_methods'][0]['total_sales'], '200.00')

    # --------------------------------------------------------------------------
    # Expense Report Tests
    # --------------------------------------------------------------------------

    def test_expense_report_html_and_json(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:expense_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/expense_report.html')
        self.assertIn('expense_data', resp.context)
        self.assertEqual(resp.context['expense_data']['total_expenses'], Decimal('30.00'))

        json_resp = self.client.get(reverse('reports:expense_report') + '?format=json')
        self.assertEqual(json_resp.status_code, 200)
        data = json_resp.json()['data']
        self.assertEqual(data['total_expenses'], '30.00')
        self.assertEqual(data['expense_count'], 1)

    def test_expense_report_alias_url(self):
        self.client.force_login(self.manager)
        resp = self.client.get('/reports/expense/?format=json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    def test_expense_report_category_filter(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:expense_report') + '?category=UTILITIES&format=json')
        self.assertEqual(resp.status_code, 200)
        recent = resp.json()['data']['recent_expenses']
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]['category'], 'UTILITIES')

    def test_expense_report_only_approved_expenses(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:expense_report') + '?period=today&format=json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        # Only self.expense_appr (30.00) should be included, not self.expense_pend (70.00)
        self.assertEqual(data['total_expenses'], '30.00')

    # --------------------------------------------------------------------------
    # Profit & Loss Report Tests
    # --------------------------------------------------------------------------

    def test_profit_report_html_and_json(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:profit_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/profit_report.html')
        self.assertIn('profit_data', resp.context)

        json_resp = self.client.get(reverse('reports:profit_report') + '?format=json')
        self.assertEqual(json_resp.status_code, 200)
        self.assertTrue(json_resp.json()['success'])

    def test_profit_report_calculation_accuracy(self):
        self.client.force_login(self.manager)
        # Revenue = 300.00 (sale_1: 200 + sale_2: 100)
        # COGS = sale_1 (2*30 + 1*60 = 120) + sale_2 (1*60 = 60) = 180.00
        # Gross profit = 300.00 - 180.00 = 120.00
        # Approved expenses = 30.00
        # Net profit = 120.00 - 30.00 = 90.00
        # Margin = (90 / 300) * 100 = 30.00%
        resp = self.client.get(reverse('reports:profit_report') + '?period=today&format=json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['revenue'], '300.00')
        self.assertEqual(data['cost_of_goods_sold'], '180.00')
        self.assertEqual(data['gross_profit'], '120.00')
        self.assertEqual(data['expenses'], '30.00')
        self.assertEqual(data['net_profit'], '90.00')
        self.assertEqual(data['profit_margin'], '30.00')

    # --------------------------------------------------------------------------
    # Growth & Trends Report Tests
    # --------------------------------------------------------------------------

    def test_growth_report_html_and_json(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:growth_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'reports/growth.html')
        self.assertIn('growth_data', resp.context)

        json_resp = self.client.get(reverse('reports:growth_report') + '?format=json')
        self.assertEqual(json_resp.status_code, 200)
        data = json_resp.json()['data']
        self.assertEqual(data['current_period_sales'], '300.00')
        self.assertEqual(data['current_period_expenses'], '30.00')
        self.assertEqual(data['current_period_profit'], '90.00')
        self.assertEqual(data['current_period_sales_count'], 2)

    def test_growth_report_week_and_month_comparison(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:growth_report') + '?period=this_week&format=json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        resp2 = self.client.get(reverse('reports:growth_report') + '?period=month&format=json')
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()['success'])

    # --------------------------------------------------------------------------
    # Validation & Edge Cases Tests
    # --------------------------------------------------------------------------

    def test_invalid_date_range_returns_400(self):
        self.client.force_login(self.manager)
        # Invalid format
        resp = self.client.get(reverse('reports:sales_report') + '?start_date=invalid-date&end_date=2026-10-06&format=json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

        # Start date after end date
        resp2 = self.client.get(reverse('reports:sales_report') + '?start_date=2026-10-10&end_date=2026-10-01&format=json')
        self.assertEqual(resp2.status_code, 400)
        self.assertFalse(resp2.json()['success'])

    def test_invalid_period_returns_400(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('reports:profit_report') + '?period=unsupported_period&format=json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    def test_disallowed_methods_return_405(self):
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('reports:reports_dashboard'))
        self.assertEqual(resp.status_code, 405)

    # --------------------------------------------------------------------------
    # Audit Logging Tests
    # --------------------------------------------------------------------------

    def test_views_log_activity_viewed(self):
        self.client.force_login(self.manager)
        count_before = ActivityLog.objects.filter(
            actor=self.manager,
            action_type=ActivityLog.ActionType.VIEWED,
        ).count()

        self.client.get(reverse('reports:reports_dashboard'))
        self.client.get(reverse('reports:sales_report'))
        self.client.get(reverse('reports:expense_report'))
        self.client.get(reverse('reports:profit_report'))
        self.client.get(reverse('reports:growth_report'))

        count_after = ActivityLog.objects.filter(
            actor=self.manager,
            action_type=ActivityLog.ActionType.VIEWED,
        ).count()
        self.assertEqual(count_after - count_before, 5)
