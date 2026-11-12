import json
from decimal import Decimal
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.inventory.models import InventoryItem
from apps.orders.models import Order, OrderItem
from apps.credits.models import CreditAccount, CreditTransaction
from apps.payments.models import Payment
from apps.payments.services import PaymentService
from apps.products.models import Product, ProductCategory

User = get_user_model()


class CustomerStorefrontTestCase(TestCase):
    """
    Comprehensive automated test suite for customer storefront templates,
    end-to-end cart/checkout flows, multi-rail payment initialization,
    inventory deduction upon payment callback, and RBAC segregation.
    """

    def setUp(self):
        # Create categories
        self.category_beverages = ProductCategory.objects.create(
            name="Beverages",
            slug="beverages",
            is_active=True,
        )
        self.category_provisions = ProductCategory.objects.create(
            name="Provisions",
            slug="provisions",
            is_active=True,
        )

        # Create products with inventory items
        self.product_juice = Product.objects.create(
            name="MADAM HY Tropical Fruit Juice",
            slug="madam-hy-tropical-fruit-juice",
            sku="MH-JCE-001",
            selling_price=Decimal("2500.00"),
            cost_price=Decimal("1800.00"),
            category=self.category_beverages,
            reorder_level=10,
            is_active=True,
            description="Pure cold-pressed tropical juice with no added sugar.",
        )
        self.inventory_juice = InventoryItem.objects.create(
            product=self.product_juice,
            quantity=50,
        )

        self.product_cereal = Product.objects.create(
            name="MADAM HY Golden Corn Flakes",
            slug="madam-hy-golden-corn-flakes",
            sku="MH-CRL-002",
            selling_price=Decimal("3800.00"),
            cost_price=Decimal("2900.00"),
            category=self.category_provisions,
            reorder_level=5,
            is_active=True,
            description="Crisp golden toasted corn flakes packed with essential vitamins.",
        )
        self.inventory_cereal = InventoryItem.objects.create(
            product=self.product_cereal,
            quantity=30,
        )

        # Create customers
        self.customer = User.objects.create_user(
            username="customer_ada",
            email="ada@example.com",
            password="SecurePassword123!",
            role="CUSTOMER",
            first_name="Ada",
            last_name="Obi",
        )
        self.other_customer = User.objects.create_user(
            username="customer_john",
            email="john@example.com",
            password="SecurePassword123!",
            role="CUSTOMER",
            first_name="John",
            last_name="Doe",
        )

        # Create staff user
        self.staff_user = User.objects.create_user(
            username="cashier_sam",
            email="sam@example.com",
            password="SecurePassword123!",
            role="CASHIER",
            first_name="Sam",
            last_name="Cashier",
        )

        # Clients
        self.anon_client = Client()
        self.client_customer = Client()
        self.client_customer.force_login(self.customer)

        self.client_other = Client()
        self.client_other.force_login(self.other_customer)

    # --------------------------------------------------------------------------
    # 1. CATALOG BROWSING & PRODUCT DETAIL MODERNIZATION
    # --------------------------------------------------------------------------

    def test_customer_can_browse_product_catalog(self):
        """Customer and guest can browse storefront catalog with hero and filters."""
        response = self.client_customer.get("/customer/products/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/products.html")
        content = response.content.decode("utf-8")
        self.assertIn("Everyday essentials, all in one place.", content)
        self.assertIn("customerProductGrid", content)
        self.assertIn("customerProductSearch", content)
        self.assertIn("MADAM HY Storefront", content)

    def test_customer_base_shell_decoupling_and_responsive_elements(self):
        """Customer storefront extends customer/base.html and is decoupled from staff admin sidebar."""
        response = self.client_customer.get("/customer/products/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/base.html")
        content = response.content.decode("utf-8")

        # 1. Header & Brand Identity
        self.assertIn("customer-header", content)
        self.assertNotIn("customer-announcement-bar", content)
        self.assertNotIn("Free delivery on orders over", content)
        self.assertIn("customerGlobalSearch", content)
        self.assertIn("customerCartBadge", content)
        self.assertIn("customerAccountDropdown", content)

        # 2. Responsive Mobile Drawer & Bottom Tab Bar
        self.assertIn("customer-mobile-drawer", content)
        self.assertIn("customerMobileMenuToggle", content)
        self.assertIn("customer-bottom-nav", content)
        self.assertIn("mobileCartBadge", content)

        # 3. Value Guarantees Footer
        self.assertIn("customer-footer", content)
        self.assertIn("footer-pillars-grid", content)
        self.assertIn("Browse the catalog", content)
        self.assertIn("Manage your shopping", content)

        # 4. Strict decoupling: No staff sidebar, staff topbar, or admin navbar elements
        self.assertNotIn('id="sidebar"', content)
        self.assertNotIn('class="sidebar"', content)
        self.assertNotIn('id="main-navbar"', content)


    def test_customer_products_json_api(self):
        """Catalog JSON API returns products list and category metadata."""
        response = self.client_customer.get("/customer/products/?format=json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        products = data.get("data", {}).get("products", [])
        self.assertGreaterEqual(len(products), 2)
        skus = [p["sku"] for p in products]
        self.assertIn("MH-JCE-001", skus)
        self.assertIn("MH-CRL-002", skus)

    def test_customer_catalog_filters_search_sorts_and_paginates(self):
        response = self.client_customer.get(
            "/customer/products/?format=json&category=beverages&sort_by=price_desc&page_size=1"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([item["sku"] for item in data["products"]], ["MH-JCE-001"])
        self.assertEqual(data["pagination"]["total_count"], 1)

        response = self.client_customer.get(
            "/customer/products/?format=json&q=MH-CRL-002&sort_by=price_asc&page_size=1"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([item["sku"] for item in data["products"]], ["MH-CRL-002"])
        self.assertEqual(data["pagination"]["total_pages"], 1)

        response = self.client_customer.get(
            "/customer/products/?format=json&sort_by=price_asc&page_size=1&page=2"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([item["sku"] for item in data["products"]], ["MH-CRL-002"])
        self.assertEqual(data["pagination"]["total_pages"], 2)

    def test_customer_product_detail_page_renders_real_product_data_and_tabs(self):
        """Product detail page renders product data without invented promotions or policies."""
        url = f"/customer/products/{self.product_juice.id}/"
        response = self.client_customer.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/product_detail.html")
        content = response.content.decode("utf-8")

        # Required DOM elements
        self.assertIn("productImage", content)
        self.assertIn("productName", content)
        self.assertIn("productPrice", content)
        self.assertIn("addToCartBtn", content)
        self.assertIn("buyNowBtn", content)
        self.assertIn("detailName", content)

        self.assertNotIn("MADAM HY Advantage", content)
        self.assertNotIn("Free / Fast Local Delivery", content)
        self.assertNotIn("Save 15%", content)

        # Brand banner and tabs
        self.assertIn("Product description", content)
        self.assertIn("Checkout options", content)
        self.assertIn("You May Also Like", content)

    def test_customer_product_detail_json_includes_related_products(self):
        """Product detail JSON response contains product metadata and related products carousel data."""
        url = f"/customer/products/{self.product_juice.id}/?format=json"
        response = self.client_customer.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        product_data = data.get("data", {}).get("product", {})
        self.assertEqual(product_data.get("id"), self.product_juice.id)
        self.assertEqual(product_data.get("sku"), "MH-JCE-001")
        self.assertIn("related_products", product_data)

    def test_customer_credit_page_uses_own_account_ledger(self):
        owner = User.objects.create_user(
            username="shop_owner", email="owner@example.com", password="SecurePassword123!", role="OWNER"
        )
        account = CreditAccount.objects.create(
            customer=self.customer,
            credit_limit=Decimal("50000.00"),
            outstanding_balance=Decimal("12500.00"),
            status=CreditAccount.Status.PARTIALLY_PAID,
            approved_by=owner,
        )
        CreditTransaction.objects.create(
            credit_account=account,
            transaction_type=CreditTransaction.TransactionType.CREDIT_PURCHASE,
            amount=Decimal("12500.00"),
            previous_balance=Decimal("0.00"),
            new_balance=Decimal("12500.00"),
            reference="ORDER-CUSTOMER-CREDIT-TEST",
        )

        response = self.client_customer.get("/customer/credit/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("50000.00", content)
        self.assertIn("12500.00", content)
        self.assertIn("Credit Purchase", content)
        self.assertNotIn("2026-08-10", content)

    # --------------------------------------------------------------------------
    # 2. CART MANAGEMENT & STATE
    # --------------------------------------------------------------------------

    def test_customer_can_add_update_remove_cart_items(self):
        """Customer can manage cart items with live subtotal and inventory validation."""
        # 1. Add juice to cart
        add_res = self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_juice.id, "quantity": 2, "action": "add"}),
            content_type="application/json",
        )
        self.assertEqual(add_res.status_code, 200)
        cart_data = add_res.json().get("data", {})
        self.assertEqual(cart_data.get("item_count"), 2)
        self.assertEqual(Decimal(str(cart_data.get("subtotal"))), Decimal("5000.00"))

        # 2. Add cereal to cart
        add_cereal = self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_cereal.id, "quantity": 1, "action": "add"}),
            content_type="application/json",
        )
        self.assertEqual(add_cereal.status_code, 200)
        cart_data = add_cereal.json().get("data", {})
        self.assertEqual(cart_data.get("item_count"), 3)

        # 3. View cart HTML page
        cart_page_res = self.client_customer.get("/customer/cart/")
        self.assertEqual(cart_page_res.status_code, 200)
        self.assertTemplateUsed(cart_page_res, "customer/cart.html")
        content = cart_page_res.content.decode("utf-8")
        self.assertIn("cartItemsList", content)
        self.assertNotIn("deliveryProgressCard", content)
        self.assertIn("Not calculated", content)
        self.assertIn("checkoutBtn", content)

        # 4. Update quantity
        update_res = self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_juice.id, "quantity": 4, "action": "update"}),
            content_type="application/json",
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["data"]["item_count"], 5)

        # 5. Remove cereal
        remove_res = self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_cereal.id, "action": "remove"}),
            content_type="application/json",
        )
        self.assertEqual(remove_res.status_code, 200)
        self.assertEqual(remove_res.json()["data"]["item_count"], 4)

    # --------------------------------------------------------------------------
    # 3. CHECKOUT & MULTI-RAIL PAYMENT INTENT INITIALIZATION
    # --------------------------------------------------------------------------

    def test_checkout_shows_cod_when_all_products_eligible(self):
        """Verify COD radio button is enabled and selectable when all cart products permit pay on delivery."""
        self.product_juice.allow_pay_on_delivery = True
        self.product_juice.save(update_fields=['allow_pay_on_delivery'])
        self.product_cereal.allow_pay_on_delivery = True
        self.product_cereal.save(update_fields=['allow_pay_on_delivery'])

        # Setup cart with eligible products
        self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_juice.id, "quantity": 1, "action": "add"}),
            content_type="application/json",
        )

        # GET checkout page
        response = self.client_customer.get("/customer/checkout/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get("allow_cod"))
        content = response.content.decode("utf-8")
        self.assertIn('id="payMethodCOD"', content)
        self.assertNotIn('id="payMethodCOD" name="payment_method" value="cod" disabled', content)

        # POST with COD should succeed
        checkout_payload = {
            "payment_method": "cod",
            "delivery_address": "12 Admiralty Way, Lekki Phase 1, Lagos",
            "customer_phone": "+2348012345678",
            "delivery_type": "Delivery",
            "notes": "Gate code 1234",
        }
        res = self.client_customer.post(
            "/customer/checkout/",
            data=json.dumps(checkout_payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data.get("success"))
        order = data.get("data", {}).get("order", {})
        self.assertEqual(order.get("payment_method"), "CASH")

    def test_checkout_disables_cod_when_product_ineligible(self):
        """Verify COD is disabled and rejected with explicit error if any cart item has allow_pay_on_delivery=False."""
        self.product_juice.allow_pay_on_delivery = False
        self.product_juice.save(update_fields=['allow_pay_on_delivery'])

        # Setup cart with ineligible product
        self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_juice.id, "quantity": 1, "action": "add"}),
            content_type="application/json",
        )

        # GET checkout page
        response = self.client_customer.get("/customer/checkout/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("allow_cod"))
        content = response.content.decode("utf-8")
        self.assertIn("Some items in your cart require upfront online payment", content)
        self.assertIn('id="payMethodCOD" name="payment_method" value="cod" disabled', content)

        # POST with COD should be rejected with 400
        checkout_payload = {
            "payment_method": "cod",
            "delivery_address": "12 Admiralty Way, Lekki Phase 1, Lagos",
            "customer_phone": "+2348012345678",
            "delivery_type": "Delivery",
        }
        res = self.client_customer.post(
            "/customer/checkout/",
            data=json.dumps(checkout_payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data.get("success"))
        expected_msg = "One or more items in your cart are not eligible for Pay on Delivery. Please pay online via Paystack."
        self.assertEqual(data.get("message"), expected_msg)

    def test_customer_checkout_paystack_redirect(self):
        """Checkout with Paystack online returns a valid authorization URL."""
        self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_cereal.id, "quantity": 1, "action": "add"}),
            content_type="application/json",
        )

        checkout_payload = {
            "payment_method": "paystack",
            "delivery_address": "Plot 5 Victoria Island, Lagos",
            "customer_phone": "+2348098765432",
            "delivery_type": "Pickup",
            "notes": "Counter collection",
        }

        paystack_response = Mock(status_code=200)
        paystack_response.json.return_value = {
            "status": True,
            "message": "Authorization URL created",
            "data": {
                "authorization_url": "https://checkout.paystack.com/test-checkout",
                "access_code": "test-access-code",
            },
        }
        with patch("apps.payments.paystack_service.requests.post", return_value=paystack_response):
            response = self.client_customer.post(
                "/customer/checkout/",
                data=json.dumps(checkout_payload),
                content_type="application/json",
                HTTP_ACCEPT="application/json",
            )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get("success"))

        payment_intent = data.get("data", {}).get("payment", {})
        self.assertEqual(payment_intent.get("provider"), "paystack")
        self.assertTrue(payment_intent.get("reference"))
        self.assertTrue(payment_intent.get("authorization_url"))
        self.assertTrue(data.get("data", {}).get("authorization_url"))

    def test_customer_checkout_rejects_qr_and_moniepoint(self):
        """Submitting payment_method='qr' or 'moniepoint' returns HTTP 400."""
        self.client_customer.post(
            "/customer/cart/items/",
            data=json.dumps({"product_id": self.product_cereal.id, "quantity": 1, "action": "add"}),
            content_type="application/json",
        )

        for disallowed in ["qr", "moniepoint", "bank_transfer", "transfer"]:
            checkout_payload = {
                "payment_method": disallowed,
                "delivery_address": "Plot 5 Victoria Island, Lagos",
                "customer_phone": "+2348098765432",
            }
            response = self.client_customer.post(
                "/customer/checkout/",
                data=json.dumps(checkout_payload),
                content_type="application/json",
                HTTP_ACCEPT="application/json",
            )
            self.assertEqual(response.status_code, 400, f"Expected 400 for payment_method '{disallowed}'")
            self.assertFalse(response.json().get("success"))

    # --------------------------------------------------------------------------
    # 4. PAYMENT CONFIRMATION CALLBACK & INVENTORY DEDUCTION
    # --------------------------------------------------------------------------

    def test_payment_confirmation_marks_order_paid_and_reduces_inventory(self):
        """
        Payment confirmation callback advances customer order to CONFIRMED
        and decrements inventory atomically with idempotency protection.
        """
        initial_stock = self.inventory_juice.quantity
        order_qty = 3

        # Create Order
        order = Order.objects.create(
            order_number="MH-ORD-TEST-001",
            customer=self.customer,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.TRANSFER,
            payment_status=Order.PaymentStatus.PENDING,
            subtotal=Decimal("7500.00"),
            total=Decimal("7500.00"),
            delivery_address="15 Marina, Lagos Island",
            customer_phone="+2348001122334",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_juice,
            quantity=order_qty,
            unit_price=self.product_juice.selling_price,
            product_name_snapshot=self.product_juice.name,
            sku_snapshot=self.product_juice.sku,
        )

        # Create linked payment
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=order.total,
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            payment_status=Payment.PaymentStatus.PENDING,
            payment_reference="PAY-REF-TEST-001",
            transaction_reference="TXN-REF-TEST-001",
        )

        # Execute confirmation callback
        result = PaymentService.confirm_webhook_payment(
            reference=payment.payment_reference,
            provider="moniepoint",
            paid_amount=order.total,
            gateway_status="success",
        )

        self.assertEqual(result.get("status"), "completed")

        # Verify Order is confirmed and stock remains untouched before fulfillment conversion
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.CONFIRMED)
        self.inventory_juice.refresh_from_db()
        self.assertEqual(self.inventory_juice.quantity, initial_stock)

        # Fulfill order by converting to sale
        staff_client = Client()
        staff_client.force_login(self.staff_user)
        convert_resp = staff_client.post(f"/orders/{order.id}/convert-to-sale/")
        self.assertEqual(convert_resp.status_code, 200)

        # Verify Inventory is reduced upon fulfillment conversion
        self.inventory_juice.refresh_from_db()
        self.assertEqual(self.inventory_juice.quantity, initial_stock - order_qty)

        # Test idempotency: calling callback again does not double-deduct inventory
        second_result = PaymentService.confirm_webhook_payment(
            reference=payment.payment_reference,
            provider="moniepoint",
            paid_amount=order.total,
            gateway_status="success",
        )
        self.assertEqual(second_result.get("status"), "already_completed")
        self.inventory_juice.refresh_from_db()
        self.assertEqual(self.inventory_juice.quantity, initial_stock - order_qty)

    # --------------------------------------------------------------------------
    # 5. ORDER DETAIL, SUCCESS PAGE & CUSTOMER SEGREGATION (RBAC)
    # --------------------------------------------------------------------------

    def test_customer_order_success_page_renders_with_receipt(self):
        """Order success page renders confirmed reference and printable receipt."""
        order = Order.objects.create(
            order_number="MH-ORD-SUCCESS-1",
            customer=self.customer,
            status=Order.OrderStatus.CONFIRMED,
            payment_method=Order.PaymentMethod.CARD,
            payment_status=Order.PaymentStatus.CONFIRMED,
            subtotal=Decimal("2500.00"),
            total=Decimal("2500.00"),
            delivery_address="Lekki Phase 1",
            customer_phone="+2348000000000",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product_juice,
            quantity=1,
            unit_price=self.product_juice.selling_price,
            product_name_snapshot=self.product_juice.name,
            sku_snapshot=self.product_juice.sku,
        )

        response = self.client_customer.get(f"/customer/orders/{order.id}/success/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customer/order_success.html")
        content = response.content.decode("utf-8")
        self.assertIn("Order Placed Successfully", content)
        self.assertIn("MH-ORD-SUCCESS-1", content)
        self.assertIn("Print Digital Receipt", content)

    def test_customer_isolation_cannot_view_other_customers_order(self):
        """Customer cannot view another customer's order (returns 403 or 404)."""
        other_order = Order.objects.create(
            order_number="MH-ORD-PRIVATE-99",
            customer=self.other_customer,
            status=Order.OrderStatus.PENDING,
            payment_method=Order.PaymentMethod.CASH,
            payment_status=Order.PaymentStatus.PENDING,
            subtotal=Decimal("5000.00"),
            total=Decimal("5000.00"),
        )

        response = self.client_customer.get(f"/customer/orders/{other_order.id}/")
        self.assertIn(response.status_code, (403, 404))

    def test_customer_cannot_access_staff_management_routes(self):
        """Customer role user is strictly denied access to staff/management endpoints."""
        staff_routes = [
            "/sales/pos/",
            "/expenses/",
            "/admin/",
        ]
        for route in staff_routes:
            response = self.client_customer.get(route)
            # Expect either HTTP 403 or redirect to login/dashboard
            self.assertIn(
                response.status_code,
                (302, 403),
                f"Customer should not have unrestricted 200 access to {route}",
            )
