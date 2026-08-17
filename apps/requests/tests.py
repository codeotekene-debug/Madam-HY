from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.products.models import Product, ProductCategory
from apps.requests.models import Request


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
