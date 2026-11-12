"""
MADAM HY SMART SHOP — FULL WEB PAGE SMOKE TEST & UI CONSISTENCY AUDIT
Validates HTTP status codes, template rendering, header/sidebar DOM presence,
and accessibility markup across Storefront, Customer, Staff, and Management views.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.products.models import Product, ProductCategory
from apps.inventory.models import InventoryItem

User = get_user_model()


class FullWebPageSmokeTests(TestCase):
    """Smoke test suite verifying all 24 core web application pages."""

    @classmethod
    def setUpTestData(cls):
        # 1. Store Staff / Owner User
        cls.owner = User.objects.create_user(
            username="test_owner",
            email="owner@example.com",
            password="StrongPassword123!",
            first_name="Owner",
            last_name="Test",
            role=User.Role.OWNER,
        )

        # 2. Store Cashier User
        cls.cashier = User.objects.create_user(
            username="test_cashier",
            email="cashier@example.com",
            password="StrongPassword123!",
            first_name="Cashier",
            last_name="Test",
            role=User.Role.CASHIER,
        )

        # 3. Store Customer User
        cls.customer = User.objects.create_user(
            username="test_customer",
            email="customer@example.com",
            password="StrongPassword123!",
            first_name="Customer",
            last_name="Test",
            role=User.Role.CUSTOMER,
        )

        # 4. Seed sample category and product for catalog rendering
        cls.category = ProductCategory.objects.create(name="Beverages", slug="beverages")
        cls.product = Product.objects.create(
            name="Premium Coffee Beans 500g",
            sku="COF-500",
            category=cls.category,
            selling_price=4500.00,
            cost_price=3000.00,
            is_active=True,
        )
        cls.inventory = InventoryItem.objects.create(
            product=cls.product,
            quantity=50,
        )

    def setUp(self):
        browser_headers = {"HTTP_ACCEPT": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        self.anon_client = Client(**browser_headers)
        self.owner_client = Client(**browser_headers)
        self.owner_client.force_login(self.owner)
        self.cashier_client = Client(**browser_headers)
        self.cashier_client.force_login(self.cashier)
        self.customer_client = Client(**browser_headers)
        self.customer_client.force_login(self.customer)

    # --------------------------------------------------------------------------
    # PUBLIC & AUTHENTICATION ENDPOINTS
    # --------------------------------------------------------------------------

    def test_root_index_redirects_to_storefront_catalog(self):
        """GET / redirects to /customer/products/."""
        response = self.anon_client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/customer/products/")

    def test_customer_login_page_renders(self):
        """GET /accounts/login/ renders customer login with design tokens and icons."""
        response = self.anon_client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")
        content = response.content.decode("utf-8")
        self.assertIn("Welcome Back", content)
        self.assertIn("loginForm", content)
        self.assertIn("variables.css", content)
        self.assertIn("bootstrap-icons", content)
        self.assertIn("Staff Login", content)

    def test_staff_portal_login_page_renders(self):
        """GET /accounts/portal/login/ renders staff portal login with internal badge."""
        response = self.anon_client.get("/accounts/portal/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/staff_login.html")
        content = response.content.decode("utf-8")
        self.assertIn("Staff Portal Sign In", content)
        self.assertIn("Staff &amp; Terminal Access", content)
        self.assertIn("staffLoginForm", content)
        self.assertIn("Customer Login", content)

    def test_customer_registration_page_renders(self):
        """GET /accounts/register/ renders customer registration without role selector."""
        response = self.anon_client.get("/accounts/register/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")
        content = response.content.decode("utf-8")
        self.assertIn("Create Your Account", content)
        self.assertIn("registerForm", content)
        self.assertNotIn('name="role"', content)
        self.assertNotIn('id="accountRole"', content)

    # --------------------------------------------------------------------------
    # CUSTOMER STOREFRONT & PORTAL ENDPOINTS
    # --------------------------------------------------------------------------

    def test_customer_products_catalog_renders(self):
        """GET /customer/products/ renders storefront catalog with hero and grid."""
        response = self.anon_client.get("/customer/products/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/products.html")
        content = response.content.decode("utf-8")
        self.assertIn("Shop Our Collection", content)
        self.assertIn("customerProductGrid", content)
        self.assertIn("customerProductSearch", content)
        self.assertIn("variables.css", content)

    def test_customer_cart_page_renders(self):
        """GET /customer/cart/ renders customer shopping cart and order summary."""
        response = self.customer_client.get("/customer/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/cart.html")
        content = response.content.decode("utf-8")
        self.assertIn("Shopping Cart", content)
        self.assertIn("cartItemsList", content)
        self.assertIn("cart-summary-panel", content)
        self.assertIn("checkoutBtn", content)

    def test_customer_checkout_page_renders(self):
        """GET /customer/checkout/ renders customer checkout and payment options."""
        response = self.customer_client.get("/customer/checkout/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/checkout.html")
        content = response.content.decode("utf-8")
        self.assertIn("Complete Your Order", content)
        self.assertIn("checkoutForm", content)
        self.assertIn("paymentMethod", content)

    def test_customer_dashboard_renders(self):
        """GET /customer/ and /customer/dashboard/ render customer shopping hub."""
        response = self.customer_client.get("/customer/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/dashboard.html")
        content = response.content.decode("utf-8")
        self.assertIn("Welcome Back", content)
        self.assertIn("totalOrders", content)
        self.assertIn("creditBalance", content)
        self.assertIn("availableCredit", content)

    def test_customer_orders_list_renders(self):
        """GET /customer/orders/ renders customer purchase history."""
        response = self.customer_client.get("/customer/orders/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("orders", content.lower())

    def test_customer_credit_page_renders(self):
        """GET /customer/credit/ renders customer store credit standing."""
        response = self.customer_client.get("/customer/credit/")
        self.assertEqual(response.status_code, 200)

    def test_customer_activity_timeline_renders(self):
        """GET /customer/activity/ renders customer activity audit timeline."""
        response = self.customer_client.get("/customer/activity/")
        self.assertEqual(response.status_code, 200)

    def test_customer_settings_page_renders(self):
        """GET /customer/settings/ renders customer account preferences."""
        response = self.customer_client.get("/customer/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/settings.html")

    def test_customer_requests_page_renders(self):
        """GET /customer/requests/ renders customer support requests."""
        response = self.customer_client.get("/customer/requests/")
        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------------------------------
    # BACK-OFFICE OPERATIONS & MANAGEMENT ENDPOINTS (OWNER / STAFF)
    # --------------------------------------------------------------------------

    def test_management_dashboard_renders_for_owner(self):
        """GET /dashboard/ renders executive owner dashboard."""
        response = self.owner_client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/owner.html")
        content = response.content.decode("utf-8")
        self.assertIn("Executive Overview", content)
        self.assertIn("salesChart", content)

    def test_management_dashboard_renders_for_cashier(self):
        """GET /dashboard/ renders operational staff dashboard for cashier."""
        response = self.cashier_client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/staff.html")
        content = response.content.decode("utf-8")
        self.assertIn("Staff Operations", content)

    def test_cashier_pos_terminal_renders(self):
        """GET /sales/pos/ renders interactive POS register."""
        response = self.cashier_client.get("/sales/pos/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sales/pos.html")
        content = response.content.decode("utf-8")
        self.assertIn("Point of Sale Register", content)
        self.assertIn("cartItems", content)
        self.assertIn("qrPaymentModal", content)

    def test_sales_history_renders(self):
        """GET /sales/history/ renders completed sales audit table."""
        response = self.owner_client.get("/sales/history/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sales/sales_history.html")
        content = response.content.decode("utf-8")
        self.assertIn("Sales History & Audit Log", content)

    def test_inventory_management_renders(self):
        """GET /inventory/ renders inventory operational table and adjustment panel."""
        response = self.owner_client.get("/inventory/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/inventory.html")
        content = response.content.decode("utf-8")
        self.assertIn("Inventory &amp; Stock Ledger", content)
        self.assertIn("inventoryTableBody", content)
        self.assertIn("inventoryDetailPanel", content)

    def test_orders_management_renders(self):
        """GET /orders/ renders orders fulfillment management table."""
        response = self.owner_client.get("/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/orders.html")
        content = response.content.decode("utf-8")
        self.assertIn("Orders &amp; Fulfillment", content)
        self.assertIn("ordersTableBody", content)

    def test_payments_management_renders(self):
        """GET /payments/ renders payments management table and reconciliation links."""
        response = self.owner_client.get("/payments/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/payments.html")
        content = response.content.decode("utf-8")
        self.assertIn("Payment Transactions &amp; Reconciliation", content)
        self.assertIn("paymentsTableBody", content)

    def test_credits_management_renders(self):
        """GET /credits/ renders customer credit ledger."""
        response = self.owner_client.get("/credits/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "credits/credits.html")
        content = response.content.decode("utf-8")
        self.assertIn("Customer Credit &amp; Debt Ledger", content)
        self.assertIn("creditsTableBody", content)

    def test_expenses_management_renders(self):
        """GET /expenses/ renders store expenses management table."""
        response = self.owner_client.get("/expenses/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "expenses/expenses.html")
        content = response.content.decode("utf-8")
        self.assertIn("Business Expenses &amp; Cost Ledger", content)
        self.assertIn("expensesTableBody", content)

    def test_reports_management_renders(self):
        """GET /reports/ renders financial reports and executive analytics."""
        response = self.owner_client.get("/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reports/reports.html")
        content = response.content.decode("utf-8")
        self.assertIn("Business Analytics &amp; Financial Reports", content)
        self.assertIn("overviewTableBody", content)

    def test_requests_management_renders(self):
        """GET /requests/ renders back-office requests management queue."""
        response = self.owner_client.get("/requests/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "requests/requests.html")
        content = response.content.decode("utf-8")
        self.assertIn("Customer &amp; Store Requests", content)
        self.assertIn("requestsTableBody", content)

    def test_activity_logs_management_renders(self):
        """GET /activity-logs/ renders system audit trails and filters."""
        response = self.owner_client.get("/activity-logs/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "activity_logs/activity_logs.html")
        content = response.content.decode("utf-8")
        self.assertIn("System Audit Trail &amp; Activity Log", content)

    def test_notifications_inbox_renders(self):
        """GET /notifications/ renders customer and staff notifications center."""
        response = self.owner_client.get("/notifications/")
        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------------------------------
    # ACCESSIBILITY, LANDMARKS & SHELL INTEGRITY
    # --------------------------------------------------------------------------

    def test_base_layout_shell_landmarks_and_a11y(self):
        """Verify that pages extending base.html include skip link, landmarks, and aria attributes."""
        response = self.owner_client.get("/dashboard/")
        content = response.content.decode("utf-8")
        self.assertIn('class="skip-link"', content)
        self.assertIn('href="#main-content"', content)
        self.assertIn('id="main-content"', content)
        self.assertIn('role="navigation"', content)
        self.assertIn('aria-label=', content)
        self.assertIn('sidebarToggle', content)
        self.assertIn('notificationBell', content)
        self.assertIn('userMenuDropdown', content)
        self.assertIn('icon-retail-pos', content)
        self.assertIn('icon-retail-credit', content)
