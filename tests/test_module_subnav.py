from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.products.models import Product, ProductCategory, ProductPriceHistory
from apps.inventory.models import InventoryItem
from apps.credits.models import CreditAccount, CreditTransaction
from apps.expenses.models import Expense
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.requests.models import Request
from apps.notifications.models import Notification

User = get_user_model()


class ModuleSubNavigationAndPermissionTests(TestCase):
    """
    Test suite for permission-aware module sub-navigation tabs across Inventory,
    Sales, Products, Credits, and Expenses modules, and backend permission enforcement.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Users
        cls.owner = User.objects.create_user(
            username="subnav_owner",
            email="subnav_owner@example.com",
            password="StrongPassword123!",
            role=User.Role.OWNER,
        )
        cls.manager = User.objects.create_user(
            username="subnav_manager",
            email="subnav_manager@example.com",
            password="StrongPassword123!",
            role=User.Role.MANAGER,
        )
        cls.cashier = User.objects.create_user(
            username="subnav_cashier",
            email="subnav_cashier@example.com",
            password="StrongPassword123!",
            role=User.Role.CASHIER,
        )
        cls.staff = User.objects.create_user(
            username="subnav_staff",
            email="subnav_staff@example.com",
            password="StrongPassword123!",
            role=User.Role.STAFF,
        )
        cls.customer = User.objects.create_user(
            username="subnav_customer",
            email="subnav_customer@example.com",
            password="StrongPassword123!",
            role=User.Role.CUSTOMER,
        )

        # 2. Seed data for catalog & inventory
        cls.category = ProductCategory.objects.create(name="Handbags", slug="handbags")
        cls.product = Product.objects.create(
            name="Classic Emerald Handbag",
            sku="HB-EM-001",
            category=cls.category,
            selling_price=Decimal("45000.00"),
            cost_price=Decimal("28000.00"),
            reorder_level=5,
            is_active=True,
        )
        cls.inventory = InventoryItem.objects.create(
            product=cls.product,
            quantity=15,
        )

        # 3. Seed data for credits
        cls.credit_account = CreditAccount.objects.create(
            customer=cls.customer,
            credit_limit=Decimal("50000.00"),
            outstanding_balance=Decimal("15000.00"),
            status=CreditAccount.Status.ACTIVE,
            approved_by=cls.owner,
        )
        cls.credit_tx = CreditTransaction.objects.create(
            credit_account=cls.credit_account,
            transaction_type=CreditTransaction.TransactionType.ADJUSTMENT,
            amount=Decimal("15000.00"),
            previous_balance=Decimal("0.00"),
            new_balance=Decimal("15000.00"),
            reference="TX-INIT-001",
            created_by=cls.owner,
        )

        # 4. Seed data for expenses
        cls.expense = Expense.objects.create(
            expense_reference="EXP-TEST-001",
            amount=Decimal("12000.00"),
            category=Expense.Category.UTILITIES,
            expense_date=date.today(),
            description="Monthly Electricity Token",
            vendor="NEPA / AEDC",
            payment_method=Expense.PaymentMethod.BANK_TRANSFER,
            status=Expense.Status.APPROVED,
            recorded_by=cls.staff,
            approved_by=cls.owner,
        )

        # 5. Seed data for orders
        cls.order = Order.objects.create(
            order_number="MH-ORD-SUBNAV-001",
            customer=cls.customer,
            created_by=cls.cashier,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal("45000.00"),
            subtotal=Decimal("45000.00"),
        )

        # 6. Seed data for payments
        cls.payment = Payment.objects.create(
            payment_reference="PMT-SUBNAV-001",
            order=cls.order,
            customer=cls.customer,
            cashier=cls.cashier,
            amount=Decimal("45000.00"),
            payment_method="CASH",
            payment_status="COMPLETED",
        )

        # 7. Seed data for requests
        cls.req = Request.objects.create(
            request_number="REQ-SUBNAV-001",
            customer=cls.customer,
            request_type=Request.RequestType.GENERAL,
            title="Inquiry on inventory restocking",
            description="When will the emerald handbags be back in stock?",
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
        )

        # 8. Seed data for notifications
        cls.notification = Notification.objects.create(
            recipient=cls.owner,
            title="Test alert",
            message="System check notification",
            notification_type=Notification.NotificationType.SYSTEM,
            priority=Notification.Priority.NORMAL,
        )

    def setUp(self):
        self.browser_headers = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        self.client = Client()
        self.browser_client = Client(**self.browser_headers)

    # =========================================================================
    # INVENTORY MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_five_inventory_subnav_tabs(self):
        """OWNER should see all 5 tabs in /inventory/."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/inventory/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-inventory-items", content)
        self.assertIn("subnav-inventory-levels", content)
        self.assertIn("subnav-inventory-movements", content)
        self.assertIn("subnav-inventory-adjustments", content)
        self.assertIn("subnav-inventory-valuation", content)

    def test_cashier_sees_only_operational_inventory_tabs(self):
        """CASHIER should see operational tabs but NOT Adjustments or Valuation."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/inventory/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-inventory-items", content)
        self.assertIn("subnav-inventory-levels", content)
        self.assertIn("subnav-inventory-movements", content)
        self.assertNotIn("subnav-inventory-adjustments", content)
        self.assertNotIn("subnav-inventory-valuation", content)

    def test_cashier_hitting_restricted_inventory_urls_receives_403(self):
        """CASHIER hitting /inventory/adjust/ or /inventory/valuation/ receives HTTP 403."""
        self.browser_client.force_login(self.cashier)

        # 1. Adjustments URL
        res_adjust = self.browser_client.get("/inventory/adjust/")
        self.assertEqual(res_adjust.status_code, 403)

        # 2. Valuation URL
        res_val = self.browser_client.get("/inventory/valuation/")
        self.assertEqual(res_val.status_code, 403)

    def test_owner_can_access_restricted_inventory_urls(self):
        """OWNER has full access to /inventory/adjust/ and /inventory/valuation/."""
        self.browser_client.force_login(self.owner)

        res_adjust = self.browser_client.get("/inventory/adjust/")
        self.assertEqual(res_adjust.status_code, 200)
        self.assertTemplateUsed(res_adjust, "inventory/add_stock.html")

        res_val = self.browser_client.get("/inventory/valuation/")
        self.assertEqual(res_val.status_code, 200)
        self.assertTemplateUsed(res_val, "inventory/valuation.html")

    # =========================================================================
    # SALES MODULE TESTS
    # =========================================================================

    def test_owner_and_cashier_see_all_sales_subnav_tabs(self):
        """OWNER and CASHIER should see POS Terminal, Sales History, and Daily Summary."""
        for user in [self.owner, self.cashier]:
            self.browser_client.force_login(user)
            response = self.browser_client.get("/sales/pos/")
            self.assertEqual(response.status_code, 200)
            content = response.content.decode("utf-8")

            self.assertIn("subnav-sales-pos", content)
            self.assertIn("subnav-sales-history", content)
            self.assertIn("subnav-sales-summary", content)

    def test_sales_summary_supports_dual_content_negotiation(self):
        """Browser visit to /sales/summary/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/sales/summary/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "sales/dashboard.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/sales/summary/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # PRODUCTS MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_products_subnav_tabs(self):
        """OWNER should see Catalog, Categories, Price History, and Add Product."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/products/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-products-catalog", content)
        self.assertIn("subnav-products-categories", content)
        self.assertIn("subnav-products-price-history", content)
        self.assertIn("subnav-products-add", content)

    def test_cashier_sees_only_catalog_and_categories_in_products(self):
        """CASHIER should see Catalog and Categories, but NOT Price History or Add Product."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/products/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-products-catalog", content)
        self.assertIn("subnav-products-categories", content)
        self.assertNotIn("subnav-products-price-history", content)
        self.assertNotIn("subnav-products-add", content)

    def test_cashier_hitting_price_history_receives_403(self):
        """CASHIER hitting /products/price-history/ receives HTTP 403."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/products/price-history/")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_access_price_history(self):
        """OWNER has full access to /products/price-history/."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/products/price-history/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/price_history.html")

    def test_products_catalog_supports_dual_content_negotiation(self):
        """Browser visit to /products/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/products/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "products/products.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/products/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    def test_customer_isolation_from_management_subnav(self):
        """CUSTOMER user never sees management sub-navigation tabs."""
        self.browser_client.force_login(self.customer)
        response = self.browser_client.get("/customer/products/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("module-subnav-container", content)

    # =========================================================================
    # CREDITS MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_credits_subnav_tabs(self):
        """OWNER should see Accounts, Transactions, Settle, and Aging/Reports tabs."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/credits/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-credits-accounts", content)
        self.assertIn("subnav-credits-transactions", content)
        self.assertIn("subnav-credits-settle", content)
        self.assertIn("subnav-credits-reports", content)

    def test_cashier_sees_operational_credits_tabs_and_reports_hidden(self):
        """CASHIER should see Accounts, Transactions, Settle, but NOT Aging/Reports."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/credits/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-credits-accounts", content)
        self.assertIn("subnav-credits-transactions", content)
        self.assertIn("subnav-credits-settle", content)
        self.assertNotIn("subnav-credits-reports", content)

    def test_staff_sees_only_accounts_and_transactions_in_credits(self):
        """STAFF should see Accounts and Transactions, but NOT Settle or Aging/Reports."""
        self.browser_client.force_login(self.staff)
        response = self.browser_client.get("/credits/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-credits-accounts", content)
        self.assertIn("subnav-credits-transactions", content)
        self.assertNotIn("subnav-credits-settle", content)
        self.assertNotIn("subnav-credits-reports", content)

    def test_unauthorized_roles_receive_403_on_restricted_credits_views(self):
        """Cashier/Staff/Customer hitting /credits/reports/ receive 403; Staff/Customer hitting /credits/payment/ receive 403."""
        # /credits/reports/ is restricted to OWNER and MANAGER
        for user in (self.cashier, self.staff, self.customer):
            self.browser_client.force_login(user)
            res = self.browser_client.get("/credits/reports/")
            self.assertEqual(res.status_code, 403, f"User {user.role} should receive 403 on /credits/reports/")

        # /credits/payment/ is restricted to OWNER, MANAGER, and CASHIER
        for user in (self.staff, self.customer):
            self.browser_client.force_login(user)
            res = self.browser_client.get("/credits/payment/")
            self.assertEqual(res.status_code, 403, f"User {user.role} should receive 403 on /credits/payment/")

    def test_owner_can_access_credits_reports(self):
        """OWNER has full access to /credits/reports/."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/credits/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credit_report.html")

    def test_credits_supports_dual_content_negotiation(self):
        """Browser visit to /credits/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/credits/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "credits/credits.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/credits/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # EXPENSES MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_expenses_subnav_tabs(self):
        """OWNER should see All Expenses, Add Expense, Categories, and Summary tabs."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/expenses/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-expenses-list", content)
        self.assertIn("subnav-expenses-create", content)
        self.assertIn("subnav-expenses-categories", content)
        self.assertIn("subnav-expenses-summary", content)

    def test_cashier_sees_only_operational_expenses_tabs(self):
        """CASHIER should see All Expenses and Add Expense, but NOT Categories or Summary."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/expenses/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-expenses-list", content)
        self.assertIn("subnav-expenses-create", content)
        self.assertNotIn("subnav-expenses-categories", content)
        self.assertNotIn("subnav-expenses-summary", content)

    def test_unauthorized_roles_receive_403_on_restricted_expenses_views(self):
        """Cashier/Staff/Customer hitting /expenses/categories/ and /expenses/summary/ receive 403."""
        for user in (self.cashier, self.staff, self.customer):
            self.browser_client.force_login(user)

            res_cat = self.browser_client.get("/expenses/categories/")
            self.assertEqual(res_cat.status_code, 403, f"User {user.role} should receive 403 on /expenses/categories/")

            res_sum = self.browser_client.get("/expenses/summary/")
            self.assertEqual(res_sum.status_code, 403, f"User {user.role} should receive 403 on /expenses/summary/")

    def test_owner_can_access_expenses_categories_and_summary(self):
        """OWNER has full access to /expenses/categories/ and /expenses/summary/."""
        self.browser_client.force_login(self.owner)

        res_cat = self.browser_client.get("/expenses/categories/")
        self.assertEqual(res_cat.status_code, 200)
        self.assertTemplateUsed(res_cat, "expenses/categories.html")

        res_sum = self.browser_client.get("/expenses/summary/")
        self.assertEqual(res_sum.status_code, 200)
        self.assertTemplateUsed(res_sum, "expenses/expense_summary.html")

    def test_expenses_supports_dual_content_negotiation(self):
        """Browser visit to /expenses/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/expenses/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "expenses/expenses.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/expenses/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # PRODUCTS: ADD PRODUCT TESTS
    # =========================================================================

    def test_owner_sees_add_product_tab_and_can_render_page(self):
        """OWNER should see Add Product tab and render /products/create/ HTML page."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/products/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("subnav-products-add", content)

        res_create = self.browser_client.get("/products/create/")
        self.assertEqual(res_create.status_code, 200)
        self.assertTemplateUsed(res_create, "products/add_product.html")

    def test_cashier_does_not_see_add_product_tab_and_gets_403(self):
        """CASHIER should NOT see Add Product tab and gets 403 on /products/create/."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/products/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("subnav-products-add", content)

        res_create = self.browser_client.get("/products/create/")
        self.assertEqual(res_create.status_code, 403)

    # =========================================================================
    # ORDERS MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_orders_subnav_tabs(self):
        """OWNER should see All Orders, Pending, Completed, and Analytics tabs."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/orders/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-orders-all", content)
        self.assertIn("subnav-orders-pending", content)
        self.assertIn("subnav-orders-completed", content)
        self.assertIn("subnav-orders-analytics", content)

    def test_cashier_sees_only_operational_orders_tabs(self):
        """CASHIER should see operational tabs, but NOT Order Analytics."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/orders/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-orders-all", content)
        self.assertIn("subnav-orders-pending", content)
        self.assertIn("subnav-orders-completed", content)
        self.assertNotIn("subnav-orders-analytics", content)

    def test_unauthorized_roles_receive_403_on_order_summary(self):
        """Cashier/Staff/Customer hitting /orders/reports/summary/ receive 403."""
        for user in (self.cashier, self.staff, self.customer):
            self.browser_client.force_login(user)
            res = self.browser_client.get("/orders/reports/summary/")
            self.assertEqual(res.status_code, 403, f"User {user.role} should receive 403 on /orders/reports/summary/")

    def test_owner_can_access_order_summary(self):
        """OWNER has full access to /orders/reports/summary/."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/orders/reports/summary/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "orders/order_summary.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/orders/reports/summary/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    def test_orders_supports_dual_content_negotiation(self):
        """Browser visit to /orders/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/orders/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "orders/orders.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/orders/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # PAYMENTS MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_payments_subnav_tabs(self):
        """OWNER should see Payment Records, Payment Methods, and Daily Reconciliation tabs."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/payments/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-payments-records", content)
        self.assertIn("subnav-payments-methods", content)
        self.assertIn("subnav-payments-reconcile", content)

    def test_cashier_sees_only_operational_payments_tabs(self):
        """CASHIER should see Records and Methods, but NOT Daily Reconciliation."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/payments/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-payments-records", content)
        self.assertIn("subnav-payments-methods", content)
        self.assertNotIn("subnav-payments-reconcile", content)

    def test_unauthorized_roles_receive_403_on_reconcile_overview(self):
        """Cashier/Staff/Customer hitting /payments/reconcile/overview/ receive 403."""
        for user in (self.cashier, self.staff, self.customer):
            self.browser_client.force_login(user)
            res = self.browser_client.get("/payments/reconcile/overview/")
            self.assertEqual(res.status_code, 403, f"User {user.role} should receive 403 on reconciliation")

    def test_owner_can_access_reconciliation(self):
        """OWNER has full access to /payments/reconcile/overview/."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/payments/reconcile/overview/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "payments/reconciliation.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/payments/reconcile/overview/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    def test_payments_supports_dual_content_negotiation(self):
        """Browser visit to /payments/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/payments/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "payments/payments.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/payments/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # REQUESTS MODULE TESTS
    # =========================================================================

    def test_owner_sees_all_requests_subnav_tabs(self):
        """OWNER should see All Requests, Create Request, Pending Approvals, and History tabs."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get("/requests/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-requests-all", content)
        self.assertIn("subnav-requests-create", content)
        self.assertIn("subnav-requests-pending", content)
        self.assertIn("subnav-requests-history", content)

    def test_cashier_sees_only_operational_requests_tabs(self):
        """CASHIER should see All Requests, Create, and History, but NOT Pending Approvals."""
        self.browser_client.force_login(self.cashier)
        response = self.browser_client.get("/requests/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-requests-all", content)
        self.assertIn("subnav-requests-create", content)
        self.assertNotIn("subnav-requests-pending", content)
        self.assertIn("subnav-requests-history", content)

    def test_requests_supports_dual_content_negotiation(self):
        """Browser visit to /requests/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.owner)
        res_html = self.browser_client.get("/requests/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "requests/requests.html")

        # JSON visit
        self.client.force_login(self.owner)
        res_json = self.client.get("/requests/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])

    # =========================================================================
    # NOTIFICATIONS MODULE TESTS
    # =========================================================================

    def test_staff_sees_all_notifications_subnav_tabs(self):
        """Staff should see All Notifications, Unread Alerts, and Notification Settings."""
        self.browser_client.force_login(self.staff)
        response = self.browser_client.get("/notifications/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("subnav-notifications-all", content)
        self.assertIn("subnav-notifications-unread", content)
        self.assertIn("subnav-notifications-settings", content)

    def test_notifications_supports_dual_content_negotiation(self):
        """Browser visit to /notifications/ renders HTML; API visit returns JSON."""
        self.browser_client.force_login(self.staff)
        res_html = self.browser_client.get("/notifications/")
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, "notifications/notifications.html")

        # JSON visit
        self.client.force_login(self.staff)
        res_json = self.client.get("/notifications/?format=json")
        self.assertEqual(res_json.status_code, 200)
        self.assertTrue(res_json.json()["success"])


