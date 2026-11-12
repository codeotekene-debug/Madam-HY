import json
import uuid
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.notifications.models import Notification
from apps.products.models import Product, ProductCategory
from apps.requests.models import Request
from apps.requests.services import RequestService


class RequestModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='req_customer',
            email='req_customer@example.com',
            password='StrongPass123!',
            first_name='Request',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='req_staff',
            email='req_staff@example.com',
            password='StrongPass123!',
            first_name='Request',
            last_name='Staff',
            role='STAFF',
        )
        self.category = ProductCategory.objects.create(
            name='Groceries',
            slug='groceries',
            description='Grocery items',
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Rice 5kg',
            slug='rice-5kg',
            sku='RICE-5KG-001',
            description='Household rice',
            selling_price=Decimal('1200.00'),
            cost_price=Decimal('800.00'),
            reorder_level=5,
        )

    def test_request_creation(self):
        request = Request.objects.create(
            request_number='REQ-1001',
            customer=self.customer,
            request_type=Request.RequestType.PRODUCT,
            title='Need a restock',
            description='Please restock rice in the shop.',
            status=Request.Status.PENDING,
            priority=Request.Priority.HIGH,
            product=self.product,
            quantity=5,
            assigned_to=self.staff,
        )

        self.assertEqual(request.request_number, 'REQ-1001')
        self.assertEqual(request.customer, self.customer)
        self.assertEqual(request.product, self.product)
        self.assertEqual(request.quantity, 5)

    def test_unique_request_number(self):
        Request.objects.create(
            request_number='REQ-UNIQUE-1',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='First request',
            description='Initial request',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
        )

        with self.assertRaises(ValidationError):
            Request.objects.create(
                request_number='REQ-UNIQUE-1',
                customer=self.customer,
                request_type=Request.RequestType.SUPPORT,
                title='Duplicate request',
                description='Duplicate number',
                status=Request.Status.PENDING,
                priority=Request.Priority.NORMAL,
            )

    def test_customer_relationship(self):
        request = Request.objects.create(
            request_number='REQ-1002',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='General support',
            description='Need help with store hours',
            status=Request.Status.REVIEWING,
            priority=Request.Priority.NORMAL,
        )
        self.assertEqual(request.customer_id, self.customer.pk)
        self.assertEqual(request.customer.role, 'CUSTOMER')

    def test_request_types(self):
        self.assertIn((Request.RequestType.PRODUCT, 'Product Request'), Request.RequestType.choices)
        self.assertIn((Request.RequestType.GENERAL, 'General Request'), Request.RequestType.choices)
        self.assertIn((Request.RequestType.SUPPORT, 'Customer Support'), Request.RequestType.choices)
        self.assertIn((Request.RequestType.OTHER, 'Other'), Request.RequestType.choices)

    def test_status_choices(self):
        self.assertIn((Request.Status.PENDING, 'Pending'), Request.Status.choices)
        self.assertIn((Request.Status.REVIEWING, 'In Review'), Request.Status.choices)
        self.assertIn((Request.Status.APPROVED, 'Approved'), Request.Status.choices)
        self.assertIn((Request.Status.PROCESSING, 'Processing'), Request.Status.choices)
        self.assertIn((Request.Status.COMPLETED, 'Completed'), Request.Status.choices)
        self.assertIn((Request.Status.REJECTED, 'Rejected'), Request.Status.choices)
        self.assertIn((Request.Status.CANCELLED, 'Cancelled'), Request.Status.choices)

    def test_priority_choices(self):
        self.assertIn((Request.Priority.LOW, 'Low'), Request.Priority.choices)
        self.assertIn((Request.Priority.NORMAL, 'Normal'), Request.Priority.choices)
        self.assertIn((Request.Priority.HIGH, 'High'), Request.Priority.choices)
        self.assertIn((Request.Priority.URGENT, 'Urgent'), Request.Priority.choices)

    def test_product_relationship(self):
        request = Request.objects.create(
            request_number='REQ-1003',
            customer=self.customer,
            request_type=Request.RequestType.PRODUCT,
            title='Restock request',
            description='Require the product to be available again.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            product=self.product,
            quantity=10,
        )
        self.assertEqual(request.product_id, self.product.pk)

    def test_product_request_validation(self):
        request = Request(
            request_number='REQ-1004',
            customer=self.customer,
            request_type=Request.RequestType.PRODUCT,
            title='Missing product',
            description='This product request is missing a product reference.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_quantity_validation(self):
        request = Request(
            request_number='REQ-1005',
            customer=self.customer,
            request_type=Request.RequestType.PRODUCT,
            title='Invalid quantity',
            description='Quantity should be positive.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            product=self.product,
            quantity=0,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_staff_assignment(self):
        request = Request.objects.create(
            request_number='REQ-1006',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='Assigned to staff',
            description='Request needs review by staff.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            assigned_to=self.staff,
        )
        self.assertEqual(request.assigned_to, self.staff)

    def test_customer_cannot_be_assigned_as_staff(self):
        request = Request(
            request_number='REQ-1007',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='Wrong assignee',
            description='Customer should not be assigned to request.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            assigned_to=self.customer,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_lifecycle_validation(self):
        request = Request(
            request_number='REQ-1008',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='Resolved too early',
            description='This request should not have a resolved_at timestamp while pending.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
            resolved_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_completed_request_requires_resolution(self):
        request = Request(
            request_number='REQ-1009',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='Completed without resolution',
            description='Cannot complete without a resolution.',
            status=Request.Status.COMPLETED,
            priority=Request.Priority.NORMAL,
        )
        with self.assertRaises(ValidationError):
            request.full_clean()

    def test_timestamp_and_resolution_behavior(self):
        request = Request.objects.create(
            request_number='REQ-1010',
            customer=self.customer,
            request_type=Request.RequestType.GENERAL,
            title='Follow up',
            description='Needs a response',
            status=Request.Status.REVIEWING,
            priority=Request.Priority.URGENT,
            assigned_to=self.staff,
        )

        self.assertIsNotNone(request.created_at)
        self.assertIsNotNone(request.updated_at)
        self.assertIsNone(request.resolved_at)

        request.status = Request.Status.COMPLETED
        request.resolution = 'Issue resolved by staff.'
        request.resolved_at = timezone.now()
        request.save()

        self.assertIsNotNone(request.resolved_at)
        self.assertEqual(request.status, Request.Status.COMPLETED)

    def test_historical_record_protection(self):
        request = Request.objects.create(
            request_number='REQ-1011',
            customer=self.customer,
            request_type=Request.RequestType.SUPPORT,
            title='Historical case',
            description='This is already resolved.',
            status=Request.Status.COMPLETED,
            priority=Request.Priority.HIGH,
            resolution='Already handled.',
            resolved_at=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            request.delete()

    def test_database_constraints(self):
        constraint_names = {constraint.name for constraint in Request._meta.constraints}
        self.assertIn('request_number_unique', constraint_names)
        self.assertIn('request_quantity_positive', constraint_names)

    def test_django_system_checks(self):
        self.assertEqual(Request.check(), [])

    def test_requests_do_not_modify_inventory(self):
        request_fields = [field.name for field in Request._meta.get_fields()]
        self.assertNotIn('inventory_item', request_fields)
        self.assertNotIn('stock_movement', request_fields)

    def test_requests_do_not_modify_sales(self):
        request_fields = [field.name for field in Request._meta.get_fields()]
        self.assertNotIn('sale', request_fields)
        self.assertNotIn('sale_item', request_fields)

    def test_requests_do_not_modify_orders(self):
        request_fields = [field.name for field in Request._meta.get_fields()]
        self.assertNotIn('order', request_fields)
        self.assertNotIn('order_item', request_fields)

    def test_requests_do_not_modify_payments(self):
        request_fields = [field.name for field in Request._meta.get_fields()]
        self.assertNotIn('payment', request_fields)
        self.assertNotIn('payment_reference', request_fields)

    def test_requests_do_not_modify_credits(self):
        request_fields = [field.name for field in Request._meta.get_fields()]
        self.assertNotIn('credit_account', request_fields)
        self.assertNotIn('credit_transaction', request_fields)


class RequestServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='srv_cust',
            email='srv_cust@example.com',
            password='Password123!',
            first_name='Service',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='srv_staff',
            email='srv_staff@example.com',
            password='Password123!',
            first_name='Service',
            last_name='Staff',
            role='STAFF',
        )
        self.manager = User.objects.create_user(
            username='srv_mgr',
            email='srv_mgr@example.com',
            password='Password123!',
            first_name='Service',
            last_name='Manager',
            role='MANAGER',
        )
        self.category = ProductCategory.objects.create(name='Snacks', slug='snacks')
        self.product = Product.objects.create(
            category=self.category,
            name='Biscuits',
            slug='biscuits',
            sku='SNK-001',
            selling_price=Decimal('250.00'),
            cost_price=Decimal('180.00'),
            reorder_level=10,
        )

    def test_service_create_request_success(self):
        req = RequestService.create_request(
            customer=self.customer,
            title='Inquiry about bulk biscuits',
            description='Can I buy 50 cartons of biscuits?',
            request_type='PRODUCT',
            priority='HIGH',
            product=self.product,
            quantity=50,
            notes='Need delivery by Friday.',
        )

        self.assertIsNotNone(req.id)
        self.assertIsNotNone(req.uuid)
        self.assertTrue(req.request_number.startswith('REQ-'))
        self.assertEqual(req.status, Request.Status.PENDING)
        self.assertEqual(req.priority, Request.Priority.HIGH)
        self.assertEqual(req.product, self.product)
        self.assertEqual(req.quantity, 50)
        self.assertEqual(req.notes, 'Need delivery by Friday.')

        # Audit log verification
        log = ActivityLog.objects.filter(object_id=str(req.id)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action_type, ActivityLog.ActionType.CREATED)

    def test_service_create_validation(self):
        with self.assertRaises(ValidationError):
            RequestService.create_request(
                customer=self.customer,
                title='',
                description='Valid description',
            )

        with self.assertRaises(ValidationError):
            RequestService.create_request(
                customer=self.customer,
                title='Valid title',
                description='',
            )

        with self.assertRaises(ValidationError):
            RequestService.create_request(
                customer=self.staff,  # Not a CUSTOMER role
                title='Valid title',
                description='Valid description',
            )

    def test_service_status_lifecycle_and_terminal_guards(self):
        req = RequestService.create_request(
            customer=self.customer,
            title='Support request',
            description='Help with receipt printing',
        )

        # Transition PENDING -> REVIEWING
        req = RequestService.update_status(req, 'REVIEWING', actor=self.staff)
        self.assertEqual(req.status, Request.Status.REVIEWING)

        # Transition REVIEWING -> APPROVED
        req = RequestService.update_status(req, 'APPROVED', actor=self.staff)
        self.assertEqual(req.status, Request.Status.APPROVED)

        # Transition APPROVED -> COMPLETED without resolution fails
        with self.assertRaises(ValidationError):
            RequestService.update_status(req, 'COMPLETED', actor=self.staff, resolution='')

        # Transition with resolution succeeds
        req = RequestService.update_status(
            req,
            'COMPLETED',
            actor=self.staff,
            resolution='Printer driver updated and test receipt printed.',
        )
        self.assertEqual(req.status, Request.Status.COMPLETED)
        self.assertIsNotNone(req.resolved_at)

        # Non-manager cannot transition from COMPLETED
        with self.assertRaises(ValidationError):
            RequestService.update_status(req, 'PENDING', actor=self.staff)

    def test_service_assign_request(self):
        req = RequestService.create_request(
            customer=self.customer,
            title='Order issue',
            description='Order #123 delayed',
        )
        self.assertEqual(req.status, Request.Status.PENDING)

        req = RequestService.assign_request(req, staff_user=self.staff, actor=self.manager)
        self.assertEqual(req.assigned_to, self.staff)
        self.assertEqual(req.status, Request.Status.REVIEWING)

        # Cannot assign to customer
        with self.assertRaises(ValidationError):
            RequestService.assign_request(req, staff_user=self.customer, actor=self.manager)

    def test_service_summary_metrics(self):
        RequestService.create_request(self.customer, 'Req 1', 'Desc 1', priority='URGENT')
        req2 = RequestService.create_request(self.customer, 'Req 2', 'Desc 2')
        RequestService.update_status(req2, 'COMPLETED', actor=self.staff, resolution='Done')

        metrics = RequestService.get_summary_metrics()
        self.assertGreaterEqual(metrics['total'], 2)
        self.assertGreaterEqual(metrics['urgent'], 1)
        self.assertGreaterEqual(metrics['completed'], 1)


class RequestCustomerWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer1 = User.objects.create_user(
            username='cust_alpha',
            email='cust_alpha@example.com',
            password='Password123!',
            first_name='Alpha',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.customer2 = User.objects.create_user(
            username='cust_beta',
            email='cust_beta@example.com',
            password='Password123!',
            first_name='Beta',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='cust_staff',
            email='cust_staff@example.com',
            password='Password123!',
            first_name='Shop',
            last_name='Staff',
            role='STAFF',
        )

    def test_customer_create_request_json(self):
        self.client.force_login(self.customer1)
        payload = {
            'title': 'Need clarification on exchange policy',
            'description': 'Can items be exchanged within 7 days of purchase?',
            'request_type': 'SUPPORT',
            'priority': 'NORMAL',
        }
        response = self.client.post(
            '/requests/create/?format=json',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['request']['title'], payload['title'])
        self.assertEqual(data['data']['request']['customer']['username'], self.customer1.username)

    def test_customer_list_own_requests_only(self):
        # Customer 1 creates 2 requests
        RequestService.create_request(self.customer1, 'Alpha 1', 'Description 1')
        RequestService.create_request(self.customer1, 'Alpha 2', 'Description 2')
        # Customer 2 creates 1 request
        RequestService.create_request(self.customer2, 'Beta 1', 'Description 3')

        self.client.force_login(self.customer1)
        response = self.client.get('/requests/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']['requests']), 2)
        for req in data['data']['requests']:
            self.assertEqual(req['customer']['username'], self.customer1.username)

    def test_customer_list_via_my_route(self):
        RequestService.create_request(self.customer1, 'My Ticket', 'My Description')
        self.client.force_login(self.customer1)
        response = self.client.get('/requests/my/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['data']['requests']), 1)
        self.assertEqual(data['data']['requests'][0]['title'], 'My Ticket')

    def test_customer_view_own_ticket_detail(self):
        req = RequestService.create_request(self.customer1, 'Self Ticket', 'Desc')
        self.client.force_login(self.customer1)
        response = self.client.get(f'/requests/{req.uuid}/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['data']['request']['title'], 'Self Ticket')

    def test_strict_customer_isolation_forbidden(self):
        """Cross-customer isolation: Customer A viewing Customer B ticket returns 403 Forbidden."""
        req_b = RequestService.create_request(self.customer2, 'Beta Secret Ticket', 'Private issue')
        self.client.force_login(self.customer1)

        # Attempt view via UUID
        response_uuid = self.client.get(f'/requests/{req_b.uuid}/?format=json')
        self.assertEqual(response_uuid.status_code, 403)
        self.assertFalse(response_uuid.json()['success'])
        self.assertIn('permission', response_uuid.json()['message'].lower())

        # Attempt view via string request_number
        response_str = self.client.get(f'/requests/{req_b.request_number}/?format=json')
        self.assertEqual(response_str.status_code, 403)

        # Attempt view via numeric primary key
        response_pk = self.client.get(f'/requests/{req_b.id}/?format=json')
        self.assertEqual(response_pk.status_code, 403)

    def test_customer_html_templates_render(self):
        RequestService.create_request(self.customer1, 'HTML Ticket', 'Desc')
        self.client.force_login(self.customer1)

        list_resp = self.client.get('/requests/')
        self.assertEqual(list_resp.status_code, 200)
        self.assertTemplateUsed(list_resp, 'customer/requests.html')

        my_resp = self.client.get('/customer/requests/')
        self.assertEqual(my_resp.status_code, 200)
        self.assertTemplateUsed(my_resp, 'customer/requests.html')


class RequestManagementWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create_user(
            username='mgmt_mgr',
            email='mgmt_mgr@example.com',
            password='Password123!',
            first_name='Store',
            last_name='Manager',
            role='MANAGER',
        )
        self.staff = User.objects.create_user(
            username='mgmt_staff',
            email='mgmt_staff@example.com',
            password='Password123!',
            first_name='Store',
            last_name='Staff',
            role='STAFF',
        )
        self.customer1 = User.objects.create_user(
            username='mgmt_cust1',
            email='mgmt_cust1@example.com',
            password='Password123!',
            first_name='Customer',
            last_name='One',
            role='CUSTOMER',
        )
        self.customer2 = User.objects.create_user(
            username='mgmt_cust2',
            email='mgmt_cust2@example.com',
            password='Password123!',
            first_name='Customer',
            last_name='Two',
            role='CUSTOMER',
        )

    def test_management_list_all_requests(self):
        RequestService.create_request(self.customer1, 'Req One', 'Desc 1')
        RequestService.create_request(self.customer2, 'Req Two', 'Desc 2')

        self.client.force_login(self.manager)
        response = self.client.get('/requests/?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['data']['requests']), 2)

    def test_management_filters_and_search(self):
        r1 = RequestService.create_request(self.customer1, 'Apples enquiry', 'Desc', priority='URGENT')
        r2 = RequestService.create_request(self.customer2, 'Bananas delivery', 'Desc', priority='LOW')
        RequestService.update_status(r2, 'APPROVED', actor=self.manager)

        self.client.force_login(self.manager)

        # Filter by priority
        res_priority = self.client.get('/requests/?format=json&priority=URGENT')
        self.assertEqual(len(res_priority.json()['data']['requests']), 1)
        self.assertEqual(res_priority.json()['data']['requests'][0]['title'], 'Apples enquiry')

        # Filter by status
        res_status = self.client.get('/requests/?format=json&status=APPROVED')
        self.assertEqual(len(res_status.json()['data']['requests']), 1)
        self.assertEqual(res_status.json()['data']['requests'][0]['title'], 'Bananas delivery')

        # Search keyword
        res_search = self.client.get('/requests/?format=json&search=Apples')
        self.assertEqual(len(res_search.json()['data']['requests']), 1)

    def test_management_status_transition_via_uuid(self):
        req = RequestService.create_request(self.customer1, 'Pending Item', 'Desc')
        self.client.force_login(self.staff)

        payload = {'status': 'REVIEWING'}
        response = self.client.post(
            f'/requests/{req.uuid}/status/?format=json',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['request']['status'], 'REVIEWING')

        # Transition to COMPLETED with resolution
        payload_complete = {
            'status': 'COMPLETED',
            'resolution': 'Fully addressed by staff.',
        }
        response_comp = self.client.post(
            f'/requests/{req.uuid}/status/?format=json',
            data=json.dumps(payload_complete),
            content_type='application/json',
        )
        self.assertEqual(response_comp.status_code, 200)
        self.assertEqual(response_comp.json()['data']['request']['status'], 'COMPLETED')

    def test_management_assignment(self):
        req = RequestService.create_request(self.customer1, 'Assign me', 'Desc')
        self.client.force_login(self.manager)

        payload = {'assigned_to': self.staff.id}
        response = self.client.post(
            f'/requests/{req.uuid}/assign/?format=json',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['request']['assignee'], self.staff.get_full_name())

    def test_management_view_any_request_detail(self):
        req = RequestService.create_request(self.customer1, 'Customer Ticket', 'Desc')
        self.client.force_login(self.staff)

        response = self.client.get(f'/requests/{req.uuid}/?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['request']['title'], 'Customer Ticket')


class RequestRBACAndSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user(
            username='sec_cust',
            email='sec_cust@example.com',
            password='Password123!',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='sec_staff',
            email='sec_staff@example.com',
            password='Password123!',
            role='STAFF',
        )
        self.req = RequestService.create_request(self.customer, 'Sec Request', 'Desc')

    def test_unauthenticated_requests_denied(self):
        res_list = self.client.get('/requests/?format=json')
        self.assertEqual(res_list.status_code, 401)

        res_detail = self.client.get(f'/requests/{self.req.uuid}/?format=json')
        self.assertEqual(res_detail.status_code, 401)

        res_status = self.client.post(
            f'/requests/{self.req.uuid}/status/?format=json',
            data=json.dumps({'status': 'REVIEWING'}),
            content_type='application/json',
        )
        self.assertEqual(res_status.status_code, 401)

    def test_customer_cannot_update_status(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            f'/requests/{self.req.uuid}/status/?format=json',
            data=json.dumps({'status': 'COMPLETED', 'resolution': 'Self closed'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_assign_staff(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            f'/requests/{self.req.uuid}/assign/?format=json',
            data=json.dumps({'assigned_to': self.staff.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class RequestValidationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user(
            username='val_cust',
            email='val_cust@example.com',
            password='Password123!',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='val_staff',
            email='val_staff@example.com',
            password='Password123!',
            role='STAFF',
        )
        self.req = RequestService.create_request(self.customer, 'Val Ticket', 'Desc')

    def test_create_validation_failures(self):
        self.client.force_login(self.customer)

        # Empty title
        resp = self.client.post(
            '/requests/create/?format=json',
            data=json.dumps({'title': '', 'description': 'Some description'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('title', resp.json()['errors'])

        # Negative quantity
        resp_qty = self.client.post(
            '/requests/create/?format=json',
            data=json.dumps({'title': 'Valid Title', 'description': 'Some description', 'quantity': -5}),
            content_type='application/json',
        )
        self.assertEqual(resp_qty.status_code, 400)

    def test_status_update_validation_failures(self):
        self.client.force_login(self.staff)

        # Missing status
        resp = self.client.post(
            f'/requests/{self.req.uuid}/status/?format=json',
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

        # Completed without resolution
        resp_res = self.client.post(
            f'/requests/{self.req.uuid}/status/?format=json',
            data=json.dumps({'status': 'COMPLETED', 'resolution': ''}),
            content_type='application/json',
        )
        self.assertEqual(resp_res.status_code, 400)
        self.assertIn('resolution', resp_res.json()['errors'])

    def test_nonexistent_request_returns_404(self):
        self.client.force_login(self.staff)
        random_uuid = uuid.uuid4()
        response = self.client.get(f'/requests/{random_uuid}/?format=json')
        self.assertEqual(response.status_code, 404)


class RequestAuditAndNotificationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user(
            username='notif_cust',
            email='notif_cust@example.com',
            password='Password123!',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='notif_staff',
            email='notif_staff@example.com',
            password='Password123!',
            role='STAFF',
        )

    def test_audit_log_and_customer_notification(self):
        # 1. Creation generates audit log
        req = RequestService.create_request(
            customer=self.customer,
            title='Audit test request',
            description='Checking activity log creation',
        )
        content_type = ContentType.objects.get_for_model(Request)
        logs = ActivityLog.objects.filter(content_type=content_type, object_id=str(req.id))
        self.assertTrue(logs.filter(action_type=ActivityLog.ActionType.CREATED).exists())

        # 2. Staff status update logs activity and notifies customer
        self.client.force_login(self.staff)
        self.client.post(
            f'/requests/{req.uuid}/status/?format=json',
            data=json.dumps({'status': 'APPROVED'}),
            content_type='application/json',
        )

        # Check updated activity log
        self.assertTrue(ActivityLog.objects.filter(content_type=content_type, object_id=str(req.id), action_type=ActivityLog.ActionType.APPROVED).exists())

        # Check in-app notification sent to customer
        customer_notifs = Notification.objects.filter(recipient=self.customer, notification_type=Notification.NotificationType.REQUEST)
        self.assertTrue(customer_notifs.exists())
        self.assertIn('Approved', customer_notifs.first().message)
