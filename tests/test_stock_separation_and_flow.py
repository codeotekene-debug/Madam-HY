import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.inventory.models import InventoryItem, StockMovement
from apps.products.forms import ProductEditForm, ProductForm
from apps.products.models import Product, ProductCategory

User = get_user_model()


class StockSeparationAndFlowTests(TestCase):
    """
    Test suite enforcing:
    1. Architectural separation between product catalog definition and stock control.
    2. Exclusion of stock_quantity from product forms and product edit templates.
    3. Inventory stock-in intake flow, audit ledger logging, and confirmation messaging.
    4. End-to-end synchronization across POS, customer storefront, and catalog views.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner_user',
            email='owner@test.com',
            password='Password123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='manager_user',
            email='manager@test.com',
            password='Password123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='cashier_user',
            email='cashier@test.com',
            password='Password123!',
            role='CASHIER',
        )
        self.customer = User.objects.create_user(
            username='customer_user',
            email='customer@test.com',
            password='Password123!',
            role='CUSTOMER',
        )

        self.category = ProductCategory.objects.create(name='Fabrics', slug='fabrics')

        self.product = Product.objects.create(
            name='Silk Chiffon Fabric',
            sku='MH-FAB-001',
            category=self.category,
            selling_price=Decimal('12000.00'),
            cost_price=Decimal('8000.00'),
            reorder_level=5,
            allow_pay_on_delivery=True,
        )
        self.inventory_item = InventoryItem.objects.create(
            product=self.product,
            quantity=0,
        )

        self.client_owner = Client()
        self.client_owner.force_login(self.owner)

        self.client_manager = Client()
        self.client_manager.force_login(self.manager)

        self.client_cashier = Client()
        self.client_cashier.force_login(self.cashier)

        self.client_customer = Client()
        self.client_customer.force_login(self.customer)

        self.client_anon = Client()

    def test_product_forms_exclude_stock_quantity(self):
        """ProductForm and ProductEditForm must not define or expose stock_quantity."""
        self.assertNotIn('stock_quantity', ProductForm.base_fields)
        self.assertNotIn('stock_quantity', ProductEditForm.base_fields)
        self.assertNotIn('quantity', ProductForm.base_fields)
        self.assertNotIn('quantity', ProductEditForm.base_fields)

        # Catalog fields must be present
        self.assertIn('name', ProductForm.base_fields)
        self.assertIn('category', ProductForm.base_fields)
        self.assertIn('sku', ProductForm.base_fields)
        self.assertIn('selling_price', ProductForm.base_fields)
        self.assertIn('cost_price', ProductForm.base_fields)
        self.assertIn('allow_pay_on_delivery', ProductForm.base_fields)

    def test_product_model_current_stock_property(self):
        """Product.current_stock and InventoryItem.current_stock must return physical stock."""
        self.assertEqual(self.product.current_stock, 0)
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertEqual(self.inventory_item.current_stock, 0)

        self.inventory_item.quantity = 15
        self.inventory_item.save(update_fields=['quantity'])

        # Refresh
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 15)
        self.assertEqual(self.product.stock_quantity, 15)
        self.assertEqual(self.inventory_item.current_stock, 15)

    def test_edit_product_page_renders_readonly_stock_badge_and_inventory_link(self):
        """
        templates/products/edit_product.html must:
        - Remove editable stock input field (editStockQty).
        - Render read-only stock indicator badge.
        - Provide direct link: /inventory/adjust/?product=<id>.
        """
        response = self.client_owner.get(f'/products/{self.product.id}/edit/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # No editable stock input
        self.assertNotIn('<input id="editStockQty"', html)

        # Read-only stock badge
        self.assertIn('Current Stock:', html)
        self.assertIn(f'/inventory/adjust/?product={self.product.id}', html)
        self.assertIn('Receive / Adjust Stock in Inventory &rarr;', html)

    def test_inventory_adjust_view_prepopulates_product_from_query_param(self):
        """GET /inventory/adjust/?product=<id> must pre-populate selected product."""
        response = self.client_manager.get(f'/inventory/adjust/?product={self.product.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.context['selected_product_id']), str(self.product.id))

        html = response.content.decode('utf-8')
        # Check that the option is marked selected
        self.assertIn(f'value="{self.product.id}" selected', html)

    def test_inventory_stock_in_flow_end_to_end(self):
        """
        Comprehensive End-to-End Workflow:
        1. Confirm initial stock is 0, POS API reports OUT_OF_STOCK and 0 quantity.
        2. Perform Stock In via /inventory/adjust/ (20 units).
        3. Verify StockMovement audit entry logged with performed_by=request.user.
        4. Verify confirmation banner: 'Successfully added 20 units to Silk Chiffon Fabric. New stock level: 20 units.'
        5. Verify POS API and Customer Storefront immediately report 20 units and IN_STOCK.
        6. Verify edit_product.html renders 'Current Stock: 20 units'.
        """
        # 1. Confirm initial 0 stock in POS products API
        pos_resp = self.client_cashier.get('/products/?page_size=100&sort_by=name')
        self.assertEqual(pos_resp.status_code, 200)
        pos_data = json.loads(pos_resp.content)['data']
        item_data = next((p for p in pos_data['products'] if p['id'] == self.product.id), None)
        self.assertIsNotNone(item_data)
        self.assertEqual(item_data['stock']['quantity'], 0)
        self.assertEqual(item_data['stock']['status'], 'OUT_OF_STOCK')

        # Confirm customer detail renders Out of Stock
        cust_resp = self.client_anon.get(f'/customer/products/{self.product.id}/')
        self.assertEqual(cust_resp.status_code, 200)
        cust_html = cust_resp.content.decode('utf-8')
        self.assertIn('Out of Stock', cust_html)

        # 2. Manager performs Stock In of 20 units
        stock_in_payload = {
            'product_id': self.product.id,
            'delta': 20,
            'movement_type': 'STOCK_IN',
            'reason': 'RESTOCK',
            'reference': 'Supplier: Textile World PO-99',
        }
        adjust_resp = self.client_manager.post(
            '/inventory/adjust/',
            data=json.dumps(stock_in_payload),
            content_type='application/json',
        )
        self.assertEqual(adjust_resp.status_code, 200)
        adjust_data = json.loads(adjust_resp.content)
        self.assertTrue(adjust_data['success'])
        self.assertEqual(
            adjust_data['message'],
            f'Successfully added 20 units to {self.product.name}. New stock level: 20 units.',
        )
        self.assertEqual(adjust_data['data']['new_quantity'], 20)

        # 3. Confirm StockMovement logged with performed_by=manager
        movement = StockMovement.objects.filter(product=self.product).latest('created_at')
        self.assertEqual(movement.quantity, 20)
        self.assertEqual(movement.previous_quantity, 0)
        self.assertEqual(movement.new_quantity, 20)
        self.assertEqual(movement.movement_type, 'STOCK_IN')
        self.assertEqual(movement.created_by, self.manager)
        self.assertEqual(movement.performed_by, self.manager)
        self.assertIn('Supplier: Textile World PO-99', movement.reference)

        # 4. Refresh POS products API -> must show 20 units and IN_STOCK immediately
        pos_resp2 = self.client_cashier.get('/products/?page_size=100&sort_by=name')
        self.assertEqual(pos_resp2.status_code, 200)
        pos_data2 = json.loads(pos_resp2.content)['data']
        item_data2 = next((p for p in pos_data2['products'] if p['id'] == self.product.id), None)
        self.assertIsNotNone(item_data2)
        self.assertEqual(item_data2['stock']['quantity'], 20)
        self.assertEqual(item_data2['stock']['status'], 'IN_STOCK')

        # 5. Customer Storefront detail -> must show In Stock immediately
        cust_resp2 = self.client_anon.get(f'/customer/products/{self.product.id}/')
        self.assertEqual(cust_resp2.status_code, 200)
        cust_html2 = cust_resp2.content.decode('utf-8')
        self.assertIn('In Stock', cust_html2)
        self.assertIn('20 units ready to dispatch', cust_html2)

        # 6. Verify edit_product.html displays updated count
        edit_resp = self.client_owner.get(f'/products/{self.product.id}/edit/')
        self.assertEqual(edit_resp.status_code, 200)
        edit_html = edit_resp.content.decode('utf-8')
        self.assertIn('Current Stock: 20 units', edit_html)

    def test_stock_in_works_for_product_without_initial_inventory_item(self):
        """Receiving stock for a newly added product that lacks an InventoryItem row creates it atomically."""
        new_prod = Product.objects.create(
            name='Linen Shirt',
            sku='MH-LIN-999',
            category=self.category,
            selling_price=Decimal('15000.00'),
        )
        self.assertFalse(InventoryItem.objects.filter(product=new_prod).exists())

        stock_in_payload = {
            'product_id': new_prod.id,
            'delta': 10,
            'movement_type': 'STOCK_IN',
            'reason': 'RESTOCK',
            'reference': 'First Batch Delivery',
        }
        resp = self.client_owner.post(
            '/inventory/adjust/',
            data=json.dumps(stock_in_payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertEqual(
            data['message'],
            f'Successfully added 10 units to {new_prod.name}. New stock level: 10 units.',
        )

        item = InventoryItem.objects.get(product=new_prod)
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.current_stock, 10)
        self.assertEqual(new_prod.current_stock, 10)

    def test_inventory_adjust_validation_error_returns_400_json(self):
        """
        Validation errors via JSON POST must return HTTP 400 with:
        {'success': False, 'message': '...', 'errors': {...}}
        """
        # 1. Missing product
        resp = self.client_manager.post(
            '/inventory/adjust/',
            data=json.dumps({'quantity': 10}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])
        self.assertIn('product', data['errors'])
        self.assertIn('errors', data)

        # 2. Invalid zero / negative quantity
        resp = self.client_manager.post(
            '/inventory/adjust/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 0}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])
        self.assertIn('quantity', data['errors'])

        # 3. Negative unit cost
        resp = self.client_manager.post(
            '/inventory/adjust/',
            data=json.dumps({'product_id': self.product.id, 'quantity': 5, 'unit_cost': -15.50}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])
        self.assertIn('unit_cost', data['errors'])

        # 4. Excessive deduction below zero
        resp = self.client_manager.post(
            '/inventory/adjust/',
            data=json.dumps({'product_id': self.product.id, 'delta': -100}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])
        self.assertIn('quantity', data['errors'])

    def test_inventory_adjust_validation_error_renders_template_with_errors(self):
        """
        Standard form submission fallback (non-JSON) renders template with form.errors at HTTP 400.
        """
        resp = self.client_manager.post(
            '/inventory/adjust/',
            data={'product_id': '', 'quantity': ''},
        )
        self.assertEqual(resp.status_code, 400)
        html = resp.content.decode('utf-8')
        self.assertIn('id="stock-form-error"', html)
        self.assertIn('Product', html)

    def test_inventory_template_has_permanent_error_container_and_onsubmit_guard(self):
        """
        The add_stock.html template must have the permanent error container and onsubmit preventDefault guard.
        """
        resp = self.client_manager.get('/inventory/adjust/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')
        self.assertIn('id="stock-form-error"', html)
        self.assertIn('alert alert-danger', html)
        self.assertIn('onsubmit="event.preventDefault(); return false;"', html)
