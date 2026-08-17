from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
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

    def test_django_system_checks(self):
        call_command('check')
