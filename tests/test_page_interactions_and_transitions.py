"""
Comprehensive Page Interaction Audit, End-to-End Request Verification,
and Fast Partial-Page SPA Navigation (HTMX Boost / Turbo Drive) Test Suite
for MADAM HY Smart Shop.

Covers:
1. Systematic crawl across all 9 operational modules and customer storefront (200 OK & context).
2. GET filter queries (search, category, status, date, pagination) preserving context.
3. Form submissions and state mutations (stock intake, expenses, credit settlements, product creation).
4. Role-based security boundaries and forbidden access (HTTP 403 enforcement).
5. Fast partial-page navigation shell configuration (CSRF meta, hx-boost/data-turbo attributes, progress bar, opt-outs).
"""

from datetime import date
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.credits.models import CreditAccount, CreditTransaction
from apps.expenses.models import Expense
from apps.inventory.models import InventoryItem, StockMovement
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product, ProductCategory, ProductPriceHistory
from apps.requests.models import Request
from apps.sales.models import Sale

User = get_user_model()


class BasePageInteractionSetup(TestCase):
    """Common test fixture setup across all interaction test suites."""

    @classmethod
    def setUpTestData(cls):
        # 1. User hierarchy
        cls.owner = User.objects.create_user(
            username="audit_owner",
            email="audit_owner@example.com",
            password="StrongPassword123!",
            first_name="Audit",
            last_name="Owner",
            role=User.Role.OWNER,
        )
        cls.manager = User.objects.create_user(
            username="audit_manager",
            email="audit_manager@example.com",
            password="StrongPassword123!",
            first_name="Audit",
            last_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.cashier = User.objects.create_user(
            username="audit_cashier",
            email="audit_cashier@example.com",
            password="StrongPassword123!",
            first_name="Audit",
            last_name="Cashier",
            role=User.Role.CASHIER,
        )
        cls.staff = User.objects.create_user(
            username="audit_staff",
            email="audit_staff@example.com",
            password="StrongPassword123!",
            first_name="Audit",
            last_name="Staff",
            role=User.Role.STAFF,
        )
        cls.customer = User.objects.create_user(
            username="audit_customer",
            email="audit_customer@example.com",
            password="StrongPassword123!",
            first_name="Audit",
            last_name="Customer",
            role=User.Role.CUSTOMER,
        )
        cls.other_customer = User.objects.create_user(
            username="other_customer",
            email="other_customer@example.com",
            password="StrongPassword123!",
            first_name="Other",
            last_name="Customer",
            role=User.Role.CUSTOMER,
        )

        # 2. Product Catalog & Inventory
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

        # 3. Credit Accounts
        cls.credit_account = CreditAccount.objects.create(
            customer=cls.customer,
            credit_limit=Decimal("50000.00"),
            outstanding_balance=Decimal("15000.00"),
            status=CreditAccount.Status.ACTIVE,
            approved_by=cls.owner,
        )
        cls.other_credit_account = CreditAccount.objects.create(
            customer=cls.other_customer,
            credit_limit=Decimal("30000.00"),
            outstanding_balance=Decimal("5000.00"),
            status=CreditAccount.Status.ACTIVE,
            approved_by=cls.owner,
        )

        # 4. Expenses
        cls.expense = Expense.objects.create(
            expense_reference="EXP-AUDIT-001",
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

        # 5. Orders
        cls.order = Order.objects.create(
            order_number="MH-ORD-AUDIT-001",
            customer=cls.customer,
            created_by=cls.cashier,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal("45000.00"),
            subtotal=Decimal("45000.00"),
        )

        # 6. Payments
        cls.payment = Payment.objects.create(
            payment_reference="PMT-AUDIT-001",
            order=cls.order,
            customer=cls.customer,
            cashier=cls.cashier,
            amount=Decimal("45000.00"),
            payment_method="CASH",
            payment_status="COMPLETED",
        )

        # 7. Customer Requests
        cls.req = Request.objects.create(
            request_number="REQ-AUDIT-001",
            customer=cls.customer,
            request_type=Request.RequestType.GENERAL,
            title="Inquiry on inventory restocking",
            description="When will the emerald handbags be back in stock?",
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
        )

        # 8. Notifications
        cls.notification = Notification.objects.create(
            recipient=cls.owner,
            title="System Audit Ready",
            message="All modules ready for systematic verification.",
            notification_type=Notification.NotificationType.SYSTEM,
            priority=Notification.Priority.NORMAL,
        )

    def setUp(self):
        self.browser_headers = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        self.client = Client()
        self.browser_client = Client(**self.browser_headers)


class SystematicModuleCrawlAndFilterTests(BasePageInteractionSetup):
    """
    Crawls all 9 operational modules and customer storefront,
    asserting 200 OK responses, template rendering, and filter query preservation.
    """

    def test_crawl_inventory_module_and_filters(self):
        """Verify Inventory endpoints with search, pagination, and filter queries."""
        self.browser_client.force_login(self.owner)

        # 1. Main inventory list with search & page
        response = self.browser_client.get(reverse("inventory:list"), {"search": "Emerald", "page": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/inventory.html")
        self.assertEqual(response.context.get("active_module"), "inventory")
        self.assertEqual(response.context.get("active_tab"), "items")

        # 2. Low-stock view
        response = self.browser_client.get(reverse("inventory:low_stock"), {"page": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/low_stock.html")
        self.assertEqual(response.context.get("active_tab"), "stock_levels")

        # 3. Movements history view
        response = self.browser_client.get(reverse("inventory:history"), {"page": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/stock_history.html")
        self.assertEqual(response.context.get("active_tab"), "movements")

        # 4. Add stock / adjustment view
        response = self.browser_client.get(reverse("inventory:add_stock"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/add_stock.html")
        self.assertEqual(response.context.get("active_tab"), "adjustments")

        # 5. Valuation report view
        response = self.browser_client.get(reverse("inventory:valuation"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/valuation.html")
        self.assertEqual(response.context.get("active_tab"), "valuation")

    def test_crawl_products_module_and_filters(self):
        """Verify Products catalog with sorting, category filters, and search."""
        self.browser_client.force_login(self.owner)

        # 1. Catalog list with filters
        response = self.browser_client.get(
            reverse("products:list"),
            {"search": "Classic", "category": "handbags", "sort_by": "price_asc", "page": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/products.html")

        # 2. Categories management
        response = self.browser_client.get(reverse("products:categories"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/categories.html")

        # 3. Add product form
        response = self.browser_client.get(reverse("products:create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/add_product.html")

        # 4. Price history view
        response = self.browser_client.get(reverse("products:price_history"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "products/price_history.html")

    def test_crawl_sales_module_and_filters(self):
        """Verify Sales POS terminal, completed sales history, and management dashboard."""
        self.browser_client.force_login(self.cashier)

        # 1. POS terminal
        response = self.browser_client.get(reverse("sales:pos"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sales/pos.html")

        # 2. Sales history with search
        response = self.browser_client.get(reverse("sales:history"), {"search": "MH", "status": "COMPLETED"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sales/sales_history.html")

        # 3. Cashier/Staff Dashboard
        response = self.browser_client.get(reverse("management_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/staff.html")

        # 4. Owner Dashboard
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("management_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/owner.html")

    def test_crawl_orders_module_and_filters(self):
        """Verify Orders list with status filter and summary report."""
        self.browser_client.force_login(self.owner)

        # 1. Order list with search & status query
        response = self.browser_client.get(reverse("orders:list"), {"search": "MH", "status": "PENDING", "page": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/orders.html")
        self.assertEqual(response.context.get("active_module"), "orders")

        # 2. Order summary report
        response = self.browser_client.get(reverse("orders:summary"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/order_summary.html")

    def test_crawl_payments_module_and_filters(self):
        """Verify Payments ledger, reconciliations, mismatches, and refunds."""
        self.browser_client.force_login(self.owner)

        # 1. Payments list
        response = self.browser_client.get(reverse("payments:list"), {"search": "PMT", "page": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/payments.html")
        self.assertEqual(response.context.get("active_module"), "payments")

        # 2. Reconcile overview
        response = self.browser_client.get(reverse("payments:reconcile_overview"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/reconciliation.html")

        # 3. Mismatches API
        self.client.force_login(self.owner)
        response = self.client.get(reverse("payments:mismatches"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))

        # 4. Refunds list API
        response = self.client.get(reverse("payments:refunds-list"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))

    def test_crawl_credits_module_and_filters(self):
        """Verify Credits ledger, transactions, settlements, and aging reports."""
        self.browser_client.force_login(self.owner)

        # 1. Main credit accounts list with search & balance filter
        response = self.browser_client.get(reverse("credits:credit_account_list"), {"search": "audit_customer", "has_balance": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credits.html")
        self.assertEqual(response.context.get("active_module"), "credits")
        self.assertEqual(response.context.get("active_tab"), "accounts")

        # 2. Credit transactions log
        response = self.browser_client.get(reverse("credits:credit_transactions"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credit_transactions.html")
        self.assertEqual(response.context.get("active_tab"), "transactions")

        # 3. Settlement payment page
        response = self.browser_client.get(reverse("credits:credit_payment"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credit_payment.html")
        self.assertIn(response.context.get("active_tab"), ("settle", "payment"))

        # 4. Aging reports
        response = self.browser_client.get(reverse("credits:credit_report"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credit_report.html")
        self.assertEqual(response.context.get("active_tab"), "reports")

    def test_crawl_expenses_module_and_filters(self):
        """Verify Expenses records, new expense entry, categories, and summary."""
        self.browser_client.force_login(self.owner)

        # 1. Main expenses list with category & status filter
        response = self.browser_client.get(
            reverse("expenses:expense_list"),
            {"search": "Electricity", "category": "UTILITIES", "status": "APPROVED", "page": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "expenses/expenses.html")
        self.assertEqual(response.context.get("active_module"), "expenses")
        self.assertEqual(response.context.get("active_tab"), "list")

        # 2. Add expense form view
        response = self.browser_client.get(reverse("expenses:expense_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "expenses/add_expense.html")
        self.assertEqual(response.context.get("active_tab"), "create")

        # 3. Expense categories
        response = self.browser_client.get(reverse("expenses:category_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "expenses/categories.html")
        self.assertEqual(response.context.get("active_tab"), "categories")

        # 4. Expense financial summary
        response = self.browser_client.get(reverse("expenses:expense_summary"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "expenses/expense_summary.html")
        self.assertEqual(response.context.get("active_tab"), "summary")

    def test_crawl_requests_module_and_filters(self):
        """Verify Requests queue and creation form."""
        self.browser_client.force_login(self.owner)

        # 1. Requests queue with search query
        response = self.browser_client.get(reverse("requests:request_list"), {"search": "Inquiry", "status": "PENDING"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "requests/requests.html")
        self.assertEqual(response.context.get("active_module"), "requests")

        # 2. Create request
        response = self.browser_client.get(reverse("requests:request_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "requests/create_request.html")

    def test_crawl_notifications_module(self):
        """Verify Notifications inbox and unread-count API."""
        self.browser_client.force_login(self.owner)

        # 1. Notifications inbox
        response = self.browser_client.get(reverse("notifications:inbox"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "notifications/notifications.html")
        self.assertEqual(response.context.get("active_module"), "notifications")

        # 2. Unread count API
        self.client.force_login(self.owner)
        response = self.client.get(reverse("notifications:unread_count"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))
        self.assertIn("unread_count", payload.get("data", {}))

    def test_crawl_customer_storefront_pages(self):
        """Verify all Customer storefront workflows for authenticated customer."""
        self.browser_client.force_login(self.customer)

        pages = [
            ("/customer/", "customer/dashboard.html"),
            ("/customer/products/", "customer/products.html"),
            ("/customer/cart/", "customer/cart.html"),
            ("/customer/orders/", "customer/orders.html"),
            ("/customer/credit/", "customer/credit.html"),
            ("/customer/requests/", "customer/requests.html"),
            ("/customer/settings/", "customer/settings.html"),
        ]

        for url, expected_template in pages:
            with self.subTest(url=url):
                response = self.browser_client.get(url)
                self.assertEqual(response.status_code, 200, f"Failed for {url}")
                self.assertTemplateUsed(response, expected_template)


class FormSubmissionAndMutationTests(BasePageInteractionSetup):
    """
    Validates state-modifying actions (POST):
    stock adjustment, expense recording, credit repayment, product creation, and CSRF protection.
    """

    def test_stock_intake_form_submission_persists_in_db(self):
        """POST /inventory/adjust/ increases stock quantity and generates a StockMovement log."""
        self.client.force_login(self.owner)
        initial_qty = self.inventory.quantity

        post_data = {
            "product": self.product.id,
            "quantity": 10,
            "reason": "Restock batch intake",
            "reference": "PO-RESTOCK-2026",
        }
        response = self.client.post(reverse("inventory:add_stock"), post_data)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, initial_qty + 10)

        movement = StockMovement.objects.filter(
            inventory_item=self.inventory,
            reference="PO-RESTOCK-2026",
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity, 10)
        self.assertEqual(movement.new_quantity, initial_qty + 10)
        self.assertEqual(movement.created_by, self.owner)

    def test_expense_creation_persists_in_db(self):
        """POST /expenses/add/ creates an Expense record with valid audit timestamps."""
        self.client.force_login(self.manager)

        post_data = {
            "amount": "8500.00",
            "category": "SUPPLIES",
            "expense_date": date.today().isoformat(),
            "vendor": "Office Depot Supplies",
            "payment_method": "CASH",
            "description": "Packaging materials and receipt printer paper",
        }
        response = self.client.post(
            reverse("expenses:expense_create"),
            post_data,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get("success"))

        new_expense = Expense.objects.filter(vendor="Office Depot Supplies").first()
        self.assertIsNotNone(new_expense)
        self.assertEqual(new_expense.amount, Decimal("8500.00"))
        self.assertEqual(new_expense.recorded_by, self.manager)

    def test_credit_repayment_settlement_persists_in_db(self):
        """POST /credits/accounts/<account_id>/repay/ records repayment and reduces balance."""
        self.client.force_login(self.cashier)
        initial_balance = self.credit_account.outstanding_balance

        post_data = {
            "amount": "5000.00",
            "payment_method": "CASH",
            "reference": "RCPT-CREDIT-001",
            "notes": "Partial customer repayment at checkout",
        }
        response = self.client.post(
            reverse("credits:credit_repay", kwargs={"account_id": self.credit_account.id}),
            post_data,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))

        self.credit_account.refresh_from_db()
        self.assertEqual(self.credit_account.outstanding_balance, initial_balance - Decimal("5000.00"))

        repayment_tx = CreditTransaction.objects.filter(
            credit_account=self.credit_account,
            reference="RCPT-CREDIT-001",
        ).first()
        self.assertIsNotNone(repayment_tx)
        self.assertEqual(repayment_tx.amount, Decimal("5000.00"))
        self.assertEqual(repayment_tx.transaction_type, CreditTransaction.TransactionType.REPAYMENT)

    def test_product_creation_json_persists_in_db(self):
        """POST /products/create/ creates Product in database."""
        self.client.force_login(self.owner)

        payload = {
            "name": "Silk Floral Scarf",
            "sku": "SF-SCARF-001",
            "category_id": self.category.id,
            "selling_price": "18000.00",
            "cost_price": "11000.00",
            "reorder_level": 4,
            "description": "Pure premium silk scarf.",
        }
        response = self.client.post(
            reverse("products:create"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get("success"))

        new_product = Product.objects.filter(sku="SF-SCARF-001").first()
        self.assertIsNotNone(new_product)
        self.assertEqual(new_product.selling_price, Decimal("18000.00"))

    def test_csrf_protection_enforced_on_unauthenticated_or_forged_posts(self):
        """Verify that state mutations enforce CSRF when csrf checks are enabled."""
        csrf_client = Client(enforce_csrf_checks=True)

        # Unauthenticated request without CSRF cookie/token must fail with 403 Forbidden
        response = csrf_client.post(
            reverse("inventory:add_stock"),
            {"product": self.product.id, "quantity": 5},
        )
        self.assertEqual(response.status_code, 403)


class RoleSecurityAndForbiddenAccessTests(BasePageInteractionSetup):
    """
    Enforces strict role boundaries and confirms restricted views return HTTP 403.
    """

    def test_cashier_forbidden_from_restricted_management_views(self):
        """CASHIER must be barred (HTTP 403) from Owner/Manager-only financial & valuation views."""
        self.browser_client.force_login(self.cashier)

        forbidden_urls = [
            reverse("inventory:valuation"),
            reverse("payments:reconcile_overview"),
            reverse("credits:credit_report"),
            reverse("expenses:expense_summary"),
            reverse("expenses:category_list"),
        ]

        for url in forbidden_urls:
            with self.subTest(url=url):
                response = self.browser_client.get(url)
                self.assertEqual(response.status_code, 403, f"Expected 403 for {url} but got {response.status_code}")

    def test_staff_forbidden_from_restricted_operational_endpoints(self):
        """STAFF must be barred (HTTP 403) from valuation and reports."""
        self.browser_client.force_login(self.staff)

        response = self.browser_client.get(reverse("inventory:valuation"))
        self.assertEqual(response.status_code, 403)

        response = self.browser_client.get(reverse("credits:credit_report"))
        self.assertEqual(response.status_code, 403)

    def test_customer_strictly_isolated_from_management_modules(self):
        """CUSTOMER role cannot access staff/management consoles."""
        self.browser_client.force_login(self.customer)

        forbidden_or_redirect_urls = [
            (reverse("inventory:list"), 302),  # Redirects customer to /customer/dashboard/
            (reverse("expenses:expense_list"), 403),
            (reverse("credits:credit_report"), 403),  # Customer barred from financial credit reports
            (reverse("management_dashboard"), 302),  # Redirects customer to /customer/dashboard/
        ]

        for url, expected_status in forbidden_or_redirect_urls:
            with self.subTest(url=url):
                response = self.browser_client.get(url)
                self.assertEqual(
                    response.status_code,
                    expected_status,
                    f"Unexpected status {response.status_code} for {url}",
                )

    def test_customer_isolation_on_credit_accounts(self):
        """A customer attempting to view another customer's credit account receives HTTP 403."""
        self.client.force_login(self.customer)

        # Attempt to access other_customer's credit account
        url = reverse("credits:credit_account_detail", kwargs={"account_id": self.other_credit_account.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)


class ProgressivePartialNavigationLayoutTests(BasePageInteractionSetup):
    """
    Validates presence of HTMX boost / Turbo Drive configuration in base layout shell,
    micro-progress bar, meta CSRF token, and explicit opt-out annotations.
    """

    def test_master_shell_renders_csrf_meta_and_navigation_router(self):
        """Ensure base.html outputs csrf-token meta, router.js, and topbar progress element."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. CSRF Token meta tag
        self.assertIn('<meta name="csrf-token"', content)

        # 2. Router script inclusion
        self.assertIn('js/core/router.js', content)

        # 3. Micro-progress bar element
        self.assertIn('id="topbarProgress"', content)
        self.assertIn('class="topbar-progress"', content)

    def test_spa_boost_attributes_mounted_on_key_containers(self):
        """Verify hx-boost and data-turbo are present on main content, topbarNav, and sidebar."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))
        content = response.content.decode("utf-8")

        # Sidebar boost
        self.assertIn('hx-boost="true"', content)
        self.assertIn('data-turbo="true"', content)

        # Main content and topbarNav
        self.assertIn('id="main-content"', content)
        self.assertIn('id="topbarNav"', content)

    def test_logout_forms_have_boost_opt_out_annotations(self):
        """Verify that logout forms opt out of SPA router interception to allow clean session termination."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))
        content = response.content.decode("utf-8")

        # Opt-out attributes
        self.assertIn('hx-boost="false"', content)
        self.assertIn('data-turbo="false"', content)
        self.assertIn('/accounts/logout/', content)

    def test_contextual_subnav_rendered_in_global_header(self):
        """Verify module subnav pills are mounted inside #topbarNav for active module."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))
        content = response.content.decode("utf-8")

        self.assertIn('class="module-subnav header-subnav"', content)
        self.assertIn('subnav-pill active', content)
        self.assertIn('Items Overview', content)
        self.assertIn('Valuation Reports', content)

    def test_sidebar_user_profile_card_removed_from_sidebar(self):
        """Verify the redundant .sidebar-user card has been removed from the sidebar markup."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))
        content = response.content.decode("utf-8")

        self.assertNotIn('class="sidebar-user"', content)
        self.assertNotIn('class="sidebar-profile"', content)

    def test_router_script_reexecution_and_lifecycle_engine_contract(self):
        """Verify static/js/core/router.js contains script re-execution, lifecycle dispatch, and asset reconciliation."""
        import os
        from django.conf import settings
        router_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'core', 'router.js')
        self.assertTrue(os.path.exists(router_path), "router.js must exist in static/js/core/")

        with open(router_path, 'r', encoding='utf-8') as f:
            js_code = f.read()

        # 1. Script re-execution routine (reexecuteScripts and reexecutePageScripts)
        self.assertIn('reexecuteScripts', js_code)
        self.assertIn('reexecutePageScripts', js_code)
        self.assertIn('document.createElement(\'script\')', js_code)
        self.assertIn('oldScript.parentNode.replaceChild(newScript, oldScript)', js_code)

        # 2. Unified lifecycle dispatch (DOMContentLoaded and page:load)
        self.assertIn('DOMContentLoaded', js_code)
        self.assertIn('page:load', js_code)
        self.assertIn("document.dispatchEvent(new Event('DOMContentLoaded'", js_code)
        self.assertIn("window.dispatchEvent(new CustomEvent('page:load'", js_code)

        # 3. Head asset reconciliation (CSS and external scripts)
        self.assertIn('reconcileHeadAssets', js_code)
        self.assertIn('head link[rel="stylesheet"]', js_code)

        # 4. Sidebar active link synchronization
        self.assertIn('updateSidebarActiveLink', js_code)
        self.assertIn('.sidebar-navigation', js_code)
        self.assertIn('aria-current', js_code)

    def test_sidebar_fallback_standard_navigation_contract(self):
        """Verify templates/base.html supports fallback standard navigation for complex data views if router errors."""
        self.browser_client.force_login(self.owner)
        response = self.browser_client.get(reverse("inventory:list"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        self.assertIn("window.location.href = targetUrl;", content)
        self.assertIn("router:error", content)

    def test_data_heavy_modules_html_responses_for_router_fetch(self):
        """Verify Reports, Growth, Audit Logs, Credits, and Expenses return HTML (not JSON) for router fetches."""
        self.browser_client.force_login(self.owner)
        router_headers = {
            "HTTP_ACCEPT": "text/html,application/xhtml+xml",
            "HTTP_X_HX_REQUEST": "true",
            "HTTP_X_TURBO_REQUEST": "true",
        }

        urls = [
            "/reports/",
            "/reports/growth/",
            "/activity-logs/",
            "/credits/",
            "/expenses/",
        ]

        for url in urls:
            response = self.browser_client.get(url, **router_headers)
            self.assertEqual(
                response.status_code,
                200,
                f"URL {url} must return 200 OK for router fetch",
            )
            content_type = response.headers.get("Content-Type", "")
            self.assertIn(
                "text/html",
                content_type,
                f"URL {url} must return text/html for router fetch, got {content_type}",
            )
            content = response.content.decode("utf-8")
            self.assertIn(
                'class="page-content"',
                content,
                f"URL {url} must contain .page-content container",
            )

