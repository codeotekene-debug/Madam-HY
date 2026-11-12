from datetime import date, timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import ActivityLogService, log_activity
from apps.products.models import Product, ProductCategory


class ActivityLogModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='activity_user',
            email='activity_user@example.com',
            password='StrongPass123!',
            first_name='Activity',
            last_name='User',
            role='MANAGER',
        )
        self.category = ProductCategory.objects.create(
            name='Office',
            slug='office',
            description='Office items',
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Notebook',
            slug='notebook',
            sku='NB-100',
            description='Notebook',
            selling_price=Decimal('25.00'),
            cost_price=Decimal('12.00'),
            reorder_level=2,
        )

    def test_activity_log_creation(self):
        log = ActivityLog.objects.create(
            actor=self.user,
            action_type=ActivityLog.ActionType.UPDATED,
            action_label='Updated product price',
            description='Changed the selling price for Notebook.',
            related_object=self.product,
            metadata={'old_price': '24.00', 'new_price': '25.00'},
        )

        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.action_type, ActivityLog.ActionType.UPDATED)
        self.assertEqual(log.action_label, 'Updated product price')
        self.assertEqual(log.related_object, self.product)
        self.assertEqual(log.metadata['new_price'], '25.00')

    def test_description_and_action_required(self):
        with self.assertRaises(ValidationError):
            ActivityLog(
                actor=self.user,
                action_type=ActivityLog.ActionType.CREATED,
                action_label='Created record',
                description='   ',
            ).full_clean()

        with self.assertRaises(ValidationError):
            ActivityLog(
                actor=self.user,
                action_type=ActivityLog.ActionType.CREATED,
                action_label='   ',
                description='A fresh record was created.',
            ).full_clean()

    def test_relationship_and_content_type_storage(self):
        log = ActivityLog.objects.create(
            actor=self.user,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='Created product',
            description='A new product was created.',
            related_object=self.product,
        )
        self.assertEqual(log.content_type, ContentType.objects.get_for_model(self.product))
        self.assertEqual(log.object_id, str(self.product.pk))
        self.assertEqual(log.related_object, self.product)

    def test_log_activity_service_helper(self):
        log = log_activity(
            actor=self.user,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='Created product',
            description='Product was created.',
            related_object=self.product,
            metadata={'sku': self.product.sku},
        )

        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.action_label, 'Created product')
        self.assertEqual(log.related_object, self.product)

    def test_newest_logs_first(self):
        first = ActivityLog.objects.create(
            actor=self.user,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='First log',
            description='Created first log.',
        )
        second = ActivityLog.objects.create(
            actor=self.user,
            action_type=ActivityLog.ActionType.UPDATED,
            action_label='Second log',
            description='Created second log.',
        )

        self.assertEqual(list(ActivityLog.objects.all()[:2]), [second, first])


class ActivityLogImmutabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='immutability_user',
            email='immutability@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.log = ActivityLog.objects.create(
            actor=self.user,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='Immutable record',
            description='This record cannot be deleted or mutated.',
            metadata={'key': 'value'},
        )

    def test_delete_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.log.delete()

        # Verify record still persists in database
        self.assertTrue(ActivityLog.objects.filter(pk=self.log.pk).exists())

    def test_mutation_raises_validation_error(self):
        self.log.description = 'Mutated description attempt'
        with self.assertRaises(ValidationError):
            self.log.save()


class ActivityLogServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username='service_mgr',
            email='mgr@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.staff = User.objects.create_user(
            username='service_staff',
            email='staff@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.category = ProductCategory.objects.create(
            name='Stationery',
            slug='stationery',
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Pen',
            slug='pen',
            sku='PEN-01',
            selling_price=Decimal('5.00'),
            cost_price=Decimal('2.00'),
            reorder_level=5,
        )

    def test_service_log_activity_with_telemetry(self):
        log = ActivityLogService.log_activity(
            actor=self.manager,
            action_type='UPDATE',
            action_label='Updated price',
            description='Pen price updated',
            related_object=self.product,
            metadata={'old_values': {'price': '4.00'}, 'new_values': {'price': '5.00'}},
            ip_address='192.168.1.50',
            user_agent='Mozilla/5.0 TestAgent',
        )
        self.assertEqual(log.action_type, ActivityLog.ActionType.UPDATED)
        self.assertEqual(log.ip_address, '192.168.1.50')
        self.assertEqual(log.user_agent, 'Mozilla/5.0 TestAgent')
        self.assertIn('price', log.changes_diff)
        self.assertEqual(log.changes_diff['price']['old'], '4.00')
        self.assertEqual(log.changes_diff['price']['new'], '5.00')

    def test_service_filtering(self):
        l1 = ActivityLogService.log_activity(
            actor=self.manager,
            action_type='CREATED',
            action_label='Created Pen',
            description='Pen item created',
            related_object=self.product,
        )
        l2 = ActivityLogService.log_activity(
            actor=self.staff,
            action_type='UPDATED',
            action_label='Stock updated',
            description='Stock increased for Pen',
            related_object=self.product,
            ip_address='10.0.0.1',
        )

        # Action filter with alias
        created_logs = ActivityLogService.get_activity_logs(action='CREATE')
        self.assertEqual(created_logs.count(), 1)
        self.assertEqual(created_logs.first(), l1)

        # Actor filter
        mgr_logs = ActivityLogService.get_activity_logs(actor_id=self.manager.id)
        self.assertEqual(mgr_logs.count(), 1)
        self.assertEqual(mgr_logs.first(), l1)

        # Entity filter
        product_logs = ActivityLogService.get_activity_logs(entity='product')
        self.assertEqual(product_logs.count(), 2)

        # Search query (by IP)
        ip_logs = ActivityLogService.get_activity_logs(search='10.0.0.1')
        self.assertEqual(ip_logs.count(), 1)
        self.assertEqual(ip_logs.first(), l2)

    def test_service_metrics(self):
        ActivityLogService.log_activity(
            actor=self.manager,
            action_type='CREATED',
            action_label='L1',
            description='D1',
        )
        ActivityLogService.log_activity(
            actor=self.manager,
            action_type='UPDATED',
            action_label='L2',
            description='D2',
        )
        metrics = ActivityLogService.get_activity_metrics()
        self.assertGreaterEqual(metrics['total_logs'], 2)
        self.assertGreaterEqual(metrics['today_logs'], 2)
        self.assertIn('CREATED', metrics['actions_breakdown'])
        self.assertTrue(len(metrics['top_actors']) > 0)


class ActivityLogViewsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='view_owner',
            email='owner@example.com',
            password='StrongPass123!',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            username='view_manager',
            email='manager@example.com',
            password='StrongPass123!',
            role='MANAGER',
        )
        self.cashier = User.objects.create_user(
            username='view_cashier',
            email='cashier@example.com',
            password='StrongPass123!',
            role='CASHIER',
        )
        self.staff = User.objects.create_user(
            username='view_staff',
            email='staff@example.com',
            password='StrongPass123!',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            username='view_customer',
            email='customer@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )
        self.log1 = ActivityLogService.log_activity(
            actor=self.manager,
            action_type='CREATED',
            action_label='Product added',
            description='Added new inventory line item.',
            ip_address='192.168.1.10',
            user_agent='Test Browser',
            metadata={'before': {'qty': 0}, 'after': {'qty': 10}},
        )
        self.log2 = ActivityLogService.log_activity(
            actor=self.owner,
            action_type='APPROVED',
            action_label='Expense approved',
            description='Approved office repairs expense.',
            ip_address='192.168.1.20',
        )

    def test_rbac_unauthenticated_requests(self):
        # HTML unauthenticated -> redirect to login
        res_html = self.client.get('/activity-logs/')
        self.assertEqual(res_html.status_code, 302)
        self.assertIn('/accounts/login/', res_html.url)

        # JSON unauthenticated -> 401 Unauthorized
        res_json = self.client.get('/activity-logs/', HTTP_ACCEPT='application/json')
        self.assertEqual(res_json.status_code, 401)
        self.assertFalse(res_json.json()['success'])

    def test_rbac_non_management_roles_rejected(self):
        for user in [self.cashier, self.staff, self.customer]:
            self.client.force_login(user)
            # List view
            res_list = self.client.get('/activity-logs/', HTTP_ACCEPT='application/json')
            self.assertEqual(res_list.status_code, 403, f"Role {user.role} should be forbidden.")
            self.assertFalse(res_list.json()['success'])

            # Detail view
            res_detail = self.client.get(f'/activity-logs/{self.log1.id}/', HTTP_ACCEPT='application/json')
            self.assertEqual(res_detail.status_code, 403, f"Role {user.role} should be forbidden from detail view.")

            # Metrics view
            res_metrics = self.client.get('/activity-logs/metrics/', HTTP_ACCEPT='application/json')
            self.assertEqual(res_metrics.status_code, 403, f"Role {user.role} should be forbidden from metrics.")

    def test_rbac_management_roles_allowed(self):
        for user in [self.owner, self.manager]:
            self.client.force_login(user)
            res_list = self.client.get('/activity-logs/', HTTP_ACCEPT='application/json')
            self.assertEqual(res_list.status_code, 200, f"Role {user.role} should be allowed.")
            self.assertTrue(res_list.json()['success'])

    def test_immutability_http_methods_rejected(self):
        self.client.force_login(self.manager)
        # POST to list -> 405
        res_post = self.client.post('/activity-logs/', HTTP_ACCEPT='application/json')
        self.assertEqual(res_post.status_code, 405)

        # PUT to detail -> 405
        res_put = self.client.put(f'/activity-logs/{self.log1.id}/', HTTP_ACCEPT='application/json')
        self.assertEqual(res_put.status_code, 405)

        # DELETE to detail -> 405
        res_delete = self.client.delete(f'/activity-logs/{self.log1.id}/', HTTP_ACCEPT='application/json')
        self.assertEqual(res_delete.status_code, 405)

    def test_activity_log_list_html(self):
        self.client.force_login(self.manager)
        res = self.client.get('/activity-logs/')
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'activity_logs/activity_logs.html')
        self.assertContains(res, 'System Audit Trail')
        self.assertContains(res, 'Product added')
        self.assertContains(res, 'Expense approved')

    def test_activity_log_list_json(self):
        self.client.force_login(self.manager)
        res = self.client.get('/activity-logs/?format=json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        logs = data['data']['logs']
        self.assertGreaterEqual(len(logs), 2)
        self.assertIn('pagination', data['data'])
        self.assertIn('metrics', data['data'])

    def test_activity_log_list_filtering(self):
        self.client.force_login(self.manager)
        # Action filter
        res_act = self.client.get('/activity-logs/?action=CREATED&format=json')
        self.assertEqual(res_act.status_code, 200)
        data = res_act.json()['data']['logs']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['action_label'], 'Product added')

        # Search filter (by IP)
        res_search = self.client.get('/activity-logs/?q=192.168.1.20&format=json')
        self.assertEqual(res_search.status_code, 200)
        data = res_search.json()['data']['logs']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['action_label'], 'Expense approved')

    def test_activity_log_detail_view(self):
        self.client.force_login(self.manager)
        # HTML
        res_html = self.client.get(f'/activity-logs/{self.log1.id}/')
        self.assertEqual(res_html.status_code, 200)
        self.assertTemplateUsed(res_html, 'activity_logs/log_detail.html')
        self.assertContains(res_html, 'Product added')
        self.assertContains(res_html, '192.168.1.10')

        # JSON
        res_json = self.client.get(f'/activity-logs/{self.log1.id}/?format=json')
        self.assertEqual(res_json.status_code, 200)
        data = res_json.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['ip_address'], '192.168.1.10')
        self.assertIn('qty', data['data']['changes_diff'])

    def test_activity_log_detail_not_found(self):
        self.client.force_login(self.manager)
        res = self.client.get('/activity-logs/999999/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.json()['success'])

    def test_activity_log_metrics_endpoint(self):
        self.client.force_login(self.owner)
        res = self.client.get('/activity-logs/metrics/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertGreaterEqual(data['data']['total_logs'], 2)
