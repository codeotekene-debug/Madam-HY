import json
import os
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .views import user_has_role

User = get_user_model()


class AuthApiTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='customeruser',
            email='customer@example.com',
            password='StrongPass123',
            first_name='Customer',
            last_name='User',
            role='CUSTOMER',
        )
        self.owner = User.objects.create_user(
            username='owneruser',
            email='owner@example.com',
            password='StrongPass123',
            first_name='Owner',
            last_name='User',
            role='OWNER',
        )

    def test_login_success_with_email(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.email, 'password': 'StrongPass123'},
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['email'], self.customer.email)
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.email, 'password': 'wrong-password'},
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data['success'])

    def test_login_rejects_inactive_user(self):
        self.customer.is_active = False
        self.customer.save(update_fields=['is_active'])

        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.email, 'password': 'StrongPass123'},
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'New',
                'last_name': 'Customer',
                'email': 'newcustomer@example.com',
                'phone': '+2348000000000',
                'role': 'CUSTOMER',
                'password': 'StrongPass456',
                'confirm_password': 'StrongPass456',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(User.objects.filter(email='newcustomer@example.com').exists())
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Another',
                'last_name': 'Customer',
                'email': self.customer.email,
                'phone': '+2348000000001',
                'role': 'CUSTOMER',
                'password': 'StrongPass456',
                'confirm_password': 'StrongPass456',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_public_customer_registration_succeeds(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Public',
                'last_name': 'Customer',
                'email': 'public@example.com',
                'phone': '+2348000000002',
                'role': 'CUSTOMER',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='public@example.com')
        self.assertEqual(user.role, 'CUSTOMER')
        self.assertTrue(response.json()['success'])

    def test_staff_registration_is_ignored_and_created_as_customer(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Staff',
                'last_name': 'User',
                'email': 'staff@example.com',
                'phone': '+2348000000003',
                'role': 'STAFF',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='staff@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(User.objects.filter(email='staff@example.com', role='STAFF').exists())

    def test_cashier_registration_is_ignored_and_created_as_customer(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Cashier',
                'last_name': 'User',
                'email': 'cashier@example.com',
                'phone': '+2348000000004',
                'role': 'CASHIER',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='cashier@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)

    def test_manager_registration_is_ignored_and_created_as_customer(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Manager',
                'last_name': 'User',
                'email': 'manager@example.com',
                'phone': '+2348000000005',
                'role': 'MANAGER',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='manager@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)

    def test_owner_registration_is_ignored_and_created_as_customer(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Owner',
                'last_name': 'User',
                'email': 'owner2@example.com',
                'phone': '+2348000000006',
                'role': 'OWNER',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='owner2@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)

    def test_rejected_registration_does_not_create_privileged_account(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Privileged',
                'last_name': 'User',
                'email': 'privileged@example.com',
                'phone': '+2348000000007',
                'role': 'STAFF',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='privileged@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(User.objects.filter(email='privileged@example.com', role='STAFF').exists())

    def test_registration_without_role_succeeds_as_customer(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Missing',
                'last_name': 'Role',
                'email': 'missingrole@example.com',
                'phone': '+2348000000008',
                'password': 'StrongPass789',
                'confirm_password': 'StrongPass789',
                'terms': 'on',
            },
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='missingrole@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.is_active)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('accounts:profile'))

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['success'])

    def test_profile_returns_current_user(self):
        self.client.login(username=self.customer.email, password='StrongPass123')

        response = self.client.get(reverse('accounts:profile'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['email'], self.customer.email)

    def test_change_password_updates_user_password(self):
        self.client.login(username=self.customer.email, password='StrongPass123')

        response = self.client.post(
            reverse('accounts:change_password'),
            {
                'current_password': 'StrongPass123',
                'new_password': 'NewStrongPass123',
                'confirm_password': 'NewStrongPass123',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertTrue(self.client.login(username=self.customer.email, password='NewStrongPass123'))

    def test_user_has_role_helper_matches_requested_roles(self):
        self.assertTrue(user_has_role(self.customer, 'CUSTOMER'))
        self.assertTrue(user_has_role(self.owner, 'OWNER'))
        self.assertFalse(user_has_role(self.customer, 'OWNER'))


class CustomerNotificationPreferencesTests(TestCase):
    def setUp(self):
        self.customer1 = User.objects.create_user(
            username='cust1',
            email='cust1@example.com',
            password='StrongPass123',
            first_name='Alice',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.customer2 = User.objects.create_user(
            username='cust2',
            email='cust2@example.com',
            password='StrongPass123',
            first_name='Bob',
            last_name='Customer',
            role='CUSTOMER',
        )
        self.manager = User.objects.create_user(
            username='manager1',
            email='manager1@example.com',
            password='StrongPass123',
            first_name='Mandy',
            last_name='Manager',
            role='MANAGER',
        )

    def test_default_notification_preferences(self):
        self.assertTrue(self.customer1.order_notifications)
        self.assertTrue(self.customer1.payment_notifications)
        self.assertTrue(self.customer1.request_notifications)
        self.assertFalse(self.customer1.promotion_notifications)
        self.assertEqual(self.customer1.preferences, {})

        prefs = self.customer1.get_notification_preferences()
        self.assertTrue(prefs['order_notifications'])
        self.assertTrue(prefs['payment_notifications'])
        self.assertTrue(prefs['request_notifications'])
        self.assertFalse(prefs['promotion_notifications'])
        self.assertTrue(prefs['orders'])
        self.assertFalse(prefs['promotions'])

        structured = self.customer1.get_preferences()
        self.assertTrue(structured['notifications']['orders'])
        self.assertFalse(structured['notifications']['promotions'])
        self.assertEqual(structured['preferences']['language'], 'en')
        self.assertEqual(structured['preferences']['currency'], 'NGN')
        self.assertEqual(structured['delivery']['preferredMethod'], 'Delivery')

    def test_settings_view_requires_authentication(self):
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

        json_response = self.client.get(reverse('accounts:settings') + '?format=json')
        self.assertEqual(json_response.status_code, 401)
        self.assertFalse(json_response.json()['success'])

    def test_settings_view_renders_html_for_authenticated_customer(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'customer/settings.html')
        self.assertEqual(response.context['user'], self.customer1)
        self.assertIn('preferences', response.context)

    def test_settings_view_returns_json_when_requested(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.get(reverse('accounts:settings') + '?format=json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['email'], self.customer1.email)
        self.assertTrue(data['preferences']['notifications']['orders'])

    def test_settings_view_rejects_non_get(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.post(reverse('accounts:settings'), {})
        self.assertEqual(response.status_code, 405)

    def test_preferences_api_requires_authentication(self):
        response = self.client.get(reverse('accounts:settings_notifications'))
        self.assertEqual(response.status_code, 401)

        post_response = self.client.post(
            reverse('accounts:settings_notifications'),
            data={'orders': False},
            content_type='application/json',
        )
        self.assertEqual(post_response.status_code, 401)

    def test_preferences_api_get_returns_current_preferences(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.get(reverse('accounts:settings_notifications'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user_id'], self.customer1.id)
        self.assertTrue(data['preferences']['notifications']['orders'])
        self.assertFalse(data['preferences']['notifications']['promotions'])

    def test_preferences_api_updates_flat_payload(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {
            'order_notifications': False,
            'promotion_notifications': True,
        }
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        self.customer1.refresh_from_db()
        self.assertFalse(self.customer1.order_notifications)
        self.assertTrue(self.customer1.promotion_notifications)
        self.assertTrue(self.customer1.payment_notifications)  # Unchanged

    def test_preferences_api_updates_nested_payload(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {
            'notifications': {
                'orders': False,
                'promotions': True,
                'requests': False,
                'payments': False,
            },
            'preferences': {
                'language': 'yo',
                'currency': 'USD',
                'marketing': True,
            },
            'delivery': {
                'preferredMethod': 'Pickup',
            },
        }
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        self.customer1.refresh_from_db()
        self.assertFalse(self.customer1.order_notifications)
        self.assertTrue(self.customer1.promotion_notifications)
        self.assertFalse(self.customer1.request_notifications)
        self.assertFalse(self.customer1.payment_notifications)
        self.assertEqual(self.customer1.preferences.get('language'), 'yo')
        self.assertEqual(self.customer1.preferences.get('currency'), 'USD')
        self.assertTrue(self.customer1.preferences.get('marketing'))
        self.assertEqual(self.customer1.preferences.get('preferred_delivery'), 'Pickup')

    def test_preferences_api_rejects_invalid_boolean_string(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {'order_notifications': 'not_a_bool'}
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid boolean value', data['message'])

    def test_preferences_api_rejects_invalid_boolean_type(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {'payment_notifications': [1, 2, 3]}
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_preferences_api_rejects_invalid_nested_structure(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {'notifications': 'not_a_dict'}
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_preferences_api_rejects_malformed_json(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data='{invalid_json:',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_customer_isolation_blocks_modifying_another_user_preferences(self):
        # Customer 1 attempts to modify Customer 2's preferences
        self.client.login(username=self.customer1.email, password='StrongPass123')
        payload = {
            'user_id': self.customer2.id,
            'order_notifications': False,
        }
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

        # Verify customer2 was not modified
        self.customer2.refresh_from_db()
        self.assertTrue(self.customer2.order_notifications)

    def test_customer_isolation_blocks_viewing_another_user_preferences(self):
        self.client.login(username=self.customer1.email, password='StrongPass123')
        response = self.client.get(
            reverse('accounts:settings_notifications') + f'?user_id={self.customer2.id}'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])

    def test_manager_can_inspect_customer_preferences(self):
        self.client.login(username=self.manager.email, password='StrongPass123')
        response = self.client.get(
            reverse('accounts:settings_notifications') + f'?user_id={self.customer1.id}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user_id'], self.customer1.id)

    def test_audit_log_created_on_preference_update(self):
        from apps.activity_logs.models import ActivityLog

        self.client.login(username=self.customer1.email, password='StrongPass123')
        initial_log_count = ActivityLog.objects.filter(
            actor=self.customer1,
            action_label='Notification Preferences Updated'
        ).count()

        payload = {
            'order_notifications': False,
            'promotion_notifications': True,
        }
        response = self.client.post(
            reverse('accounts:settings_notifications'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        logs = ActivityLog.objects.filter(
            actor=self.customer1,
            action_label='Notification Preferences Updated'
        )
        self.assertEqual(logs.count(), initial_log_count + 1)
        latest_log = logs.latest('created_at')
        self.assertEqual(latest_log.action_type, ActivityLog.ActionType.UPDATED)
        self.assertIn('changes', latest_log.metadata)
        self.assertIn('order_notifications', latest_log.metadata['changes'])
        self.assertEqual(latest_log.metadata['changes']['order_notifications']['old'], True)
        self.assertEqual(latest_log.metadata['changes']['order_notifications']['new'], False)


class GlobalNavigationAndErrorPagesTests(TestCase):
    """Automated tests for Global Navigation Links, Role Gating & Custom Error Pages."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email='nav_owner@test.com',
            username='nav_owner',
            password='TestPassword123',
            role='OWNER',
        )
        self.manager = User.objects.create_user(
            email='nav_manager@test.com',
            username='nav_manager',
            password='TestPassword123',
            role='MANAGER',
        )
        self.staff = User.objects.create_user(
            email='nav_staff@test.com',
            username='nav_staff',
            password='TestPassword123',
            role='STAFF',
        )
        self.customer = User.objects.create_user(
            email='nav_customer@test.com',
            username='nav_customer',
            password='TestPassword123',
            role='CUSTOMER',
        )

    def test_unauthenticated_navigation_links(self):
        """Unauthenticated visitor sees brand login link and no internal role navigation."""
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)

    def test_customer_navigation_links_and_isolation(self):
        """Customer user sees customer store links and does not see staff/owner menus."""
        self.client.force_login(self.customer)
        response = self.client.get('/customer/')
        self.assertEqual(response.status_code, 200)

        # Brand links to customer dashboard
        self.assertContains(response, 'href="/customer/"')
        self.assertContains(response, 'href="/customer/products/"')
        self.assertContains(response, 'href="/customer/cart/"')
        self.assertContains(response, 'href="/customer/orders/"')
        self.assertContains(response, 'href="/customer/credit/"')
        self.assertContains(response, 'href="/customer/requests/"')
        self.assertContains(response, 'href="/customer/activity/"')
        self.assertContains(response, 'href="/customer/settings/"')

        # Owner/staff-only links must NOT appear
        self.assertNotContains(response, 'href="/inventory/"')
        self.assertNotContains(response, 'href="/expenses/"')
        self.assertNotContains(response, 'href="/activity-logs/"')
        self.assertNotContains(response, 'href="/admin/"')

    def test_staff_navigation_links_and_isolation(self):
        """Staff user sees operations links and does not see owner-only analytics or admin."""
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        # Brand links to /dashboard/
        self.assertContains(response, 'href="/dashboard/"')
        self.assertContains(response, 'href="/sales/"')
        self.assertContains(response, 'href="/orders/"')
        self.assertContains(response, 'href="/payments/"')

        # Owner-only analytics and administration must NOT appear for staff
        self.assertNotContains(response, 'href="/reports/"')
        self.assertNotContains(response, 'href="/reports/growth/"')
        self.assertNotContains(response, 'href="/admin/"')
        self.assertNotContains(response, 'href="/customer/cart/"')

    def test_owner_navigation_links(self):
        """Owner user sees business, operations, analytics, and administration links."""
        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'href="/products/"')
        self.assertContains(response, 'href="/inventory/"')
        self.assertContains(response, 'href="/sales/"')
        self.assertContains(response, 'href="/credits/"')
        self.assertContains(response, 'href="/expenses/"')
        self.assertContains(response, 'href="/reports/"')
        self.assertContains(response, 'href="/reports/growth/"')
        self.assertContains(response, 'href="/activity-logs/"')
        self.assertContains(response, 'href="/admin/"')
        self.assertContains(response, 'href="/accounts/profile/"')

    def test_logout_post_redirects_browser_to_login(self):
        """POST to /accounts/logout/ from browser logs out and redirects to login."""
        self.client.force_login(self.customer)
        response = self.client.post('/accounts/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_logout_post_returns_json_when_requested(self):
        """POST to /accounts/logout/?format=json returns JSON response."""
        self.client.force_login(self.customer)
        response = self.client.post('/accounts/logout/?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_customer_credit_view(self):
        """Customer can access /customer/credit/ while unauthenticated/staff are redirected."""
        self.client.force_login(self.customer)
        response = self.client.get('/customer/credit/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'customer/credit.html')

        # Staff user is redirected away to management dashboard
        self.client.force_login(self.staff)
        resp_staff = self.client.get('/customer/credit/')
        self.assertEqual(resp_staff.status_code, 302)
        self.assertEqual(resp_staff.url, '/dashboard/')

    def test_customer_activity_view(self):
        """Customer can access /customer/activity/ while unauthenticated/staff are redirected."""
        self.client.force_login(self.customer)
        response = self.client.get('/customer/activity/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'customer/activity.html')

        # Staff user is redirected away to management dashboard
        self.client.force_login(self.staff)
        resp_staff = self.client.get('/customer/activity/')
        self.assertEqual(resp_staff.status_code, 302)
        self.assertEqual(resp_staff.url, '/dashboard/')

    def test_custom_403_view_html(self):
        """Custom 403 handler renders 403.html with 403 status code."""
        from django.test import RequestFactory
        from config.views import custom_403_view
        factory = RequestFactory()
        request = factory.get('/forbidden/')
        request.user = self.customer
        response = custom_403_view(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b'403 Forbidden', response.content)
        self.assertIn(b'Access Restricted', response.content)

    def test_custom_403_view_json(self):
        """Custom 403 handler returns JSON when requested."""
        from django.test import RequestFactory
        from config.views import custom_403_view
        factory = RequestFactory()
        request = factory.get('/forbidden/?format=json')
        request.user = self.customer
        response = custom_403_view(request)
        self.assertEqual(response.status_code, 403)
        import json
        payload = json.loads(response.content.decode('utf-8'))
        self.assertFalse(payload['success'])
        self.assertEqual(payload['status_code'], 403)

    def test_custom_404_view_html(self):
        """Custom 404 handler renders 404.html with 404 status code."""
        from django.test import RequestFactory
        from config.views import custom_404_view
        factory = RequestFactory()
        request = factory.get('/nonexistent-path/')
        request.user = self.customer
        response = custom_404_view(request)
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'404 Not Found', response.content)
        self.assertIn(b'Page Not Found', response.content)

    def test_custom_404_view_json(self):
        """Custom 404 handler returns JSON when requested."""
        from django.test import RequestFactory
        from config.views import custom_404_view
        factory = RequestFactory()
        request = factory.get('/nonexistent-path/?format=json')
        request.user = self.customer
        response = custom_404_view(request)
        self.assertEqual(response.status_code, 404)
        import json
        payload = json.loads(response.content.decode('utf-8'))
        self.assertFalse(payload['success'])
        self.assertEqual(payload['status_code'], 404)

    def test_custom_500_view_html(self):
        """Custom 500 handler renders 500.html with 500 status code."""
        from django.test import RequestFactory
        from config.views import custom_500_view
        factory = RequestFactory()
        request = factory.get('/server-error/')
        request.user = self.owner
        response = custom_500_view(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'500 Server Error', response.content)
        self.assertIn(b'Unexpected Error', response.content)

    def test_custom_500_view_json(self):
        """Custom 500 handler returns JSON when requested."""
        from django.test import RequestFactory
        from config.views import custom_500_view
        factory = RequestFactory()
        request = factory.get('/server-error/?format=json')
        request.user = self.owner
        response = custom_500_view(request)
        self.assertEqual(response.status_code, 500)
        import json
        payload = json.loads(response.content.decode('utf-8'))
        self.assertFalse(payload['success'])
        self.assertEqual(payload['status_code'], 500)

class SecurityConfigurationTests(TestCase):
    """
    Automated verification of settings hardening and security configuration.
    Validates DEBUG=False production enforcement vs DEBUG=True local development behavior.
    """

    def test_env_bool_parser(self):
        from config.settings import env_bool
        from unittest.mock import patch

        with patch.dict(os.environ, {'TEST_BOOL_TRUE': 'True', 'TEST_BOOL_1': '1', 'TEST_BOOL_YES': 'yes'}):
            self.assertTrue(env_bool('TEST_BOOL_TRUE'))
            self.assertTrue(env_bool('TEST_BOOL_1'))
            self.assertTrue(env_bool('TEST_BOOL_YES'))

        with patch.dict(os.environ, {'TEST_BOOL_FALSE': 'False', 'TEST_BOOL_0': '0', 'TEST_BOOL_NO': 'no'}):
            self.assertFalse(env_bool('TEST_BOOL_FALSE'))
            self.assertFalse(env_bool('TEST_BOOL_0'))
            self.assertFalse(env_bool('TEST_BOOL_NO'))

        self.assertFalse(env_bool('NON_EXISTENT_VAR', default=False))
        self.assertTrue(env_bool('NON_EXISTENT_VAR', default=True))

    def test_env_int_parser(self):
        from config.settings import env_int
        from unittest.mock import patch

        with patch.dict(os.environ, {'TEST_INT': '31536000', 'TEST_INVALID': 'not_a_number'}):
            self.assertEqual(env_int('TEST_INT', default=0), 31536000)
            self.assertEqual(env_int('TEST_INVALID', default=100), 100)
        self.assertEqual(env_int('NON_EXISTENT_INT', default=42), 42)

    def test_parse_database_url(self):
        from config.settings import parse_database_url

        sqlite_conf = parse_database_url('sqlite:///db.sqlite3')
        self.assertEqual(sqlite_conf['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(sqlite_conf['NAME'], 'db.sqlite3')

        sqlite_mem = parse_database_url('sqlite:///:memory:')
        self.assertEqual(sqlite_mem['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(sqlite_mem['NAME'], ':memory:')

        mysql_conf = parse_database_url('mysql://appuser:mypassword@db.internal:3306/smart_shop_prod')
        self.assertEqual(mysql_conf['ENGINE'], 'django.db.backends.mysql')
        self.assertEqual(mysql_conf['NAME'], 'smart_shop_prod')
        self.assertEqual(mysql_conf['USER'], 'appuser')
        self.assertEqual(mysql_conf['PASSWORD'], 'mypassword')
        self.assertEqual(mysql_conf['HOST'], 'db.internal')
        self.assertEqual(mysql_conf['PORT'], '3306')
        self.assertEqual(mysql_conf['OPTIONS'], {'charset': 'utf8mb4'})

    def test_production_secret_key_validation(self):
        insecure_keys = [
            '',
            'django-insecure-test-key-12345',
            'change-this-to-a-random-secret-key',
            'too-short-key',
            '123456789012345678901234567890123456789012345',  # 45 chars (< 50)
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',  # 50 chars, but 1 unique char (< 5)
        ]

        for bad_key in insecure_keys:
            with self.subTest(key=bad_key):
                is_insecure = (
                    not bad_key
                    or bad_key.startswith('django-insecure-')
                    or bad_key == 'change-this-to-a-random-secret-key'
                    or len(bad_key) < 50
                    or len(set(bad_key)) < 5
                )
                self.assertTrue(is_insecure)

    def test_production_allowed_hosts_validation(self):
        for bad_hosts in [[], ['*'], ['smartshop.example.com', '*']]:
            with self.subTest(hosts=bad_hosts):
                is_invalid = not bad_hosts or '*' in bad_hosts
                self.assertTrue(is_invalid)

    def test_production_secret_key_raises_improperly_configured(self):
        """DEBUG=False strictly disallows short or insecure fallback SECRET_KEY."""
        import subprocess
        import sys

        env = os.environ.copy()
        env['DEBUG'] = 'False'
        env['SECRET_KEY'] = 'too-short-secret-key'
        env['ALLOWED_HOSTS'] = 'smartshop.example.com'

        cmd = [
            sys.executable,
            '-c',
            'import os; os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"; import django; django.setup()'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
        self.assertIn('SECRET_KEY', result.stderr)

    def test_production_allowed_hosts_raises_improperly_configured(self):
        """DEBUG=False strictly disallows wildcard '*' or empty ALLOWED_HOSTS."""
        import subprocess
        import sys

        env = os.environ.copy()
        env['DEBUG'] = 'False'
        env['SECRET_KEY'] = 'c8v2j8w9e0r1t3y5u7i9o1p3a5s7d9f1g3h5j7k9l1z3x5c7v9b1n3m5'
        env['ALLOWED_HOSTS'] = '*'

        cmd = [
            sys.executable,
            '-c',
            'import os; os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"; import django; django.setup()'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
        self.assertIn('ALLOWED_HOSTS', result.stderr)

    def test_security_headers_production_vs_development(self):
        """Verify toggleable security headers behavior between production and development."""
        import subprocess
        import sys

        valid_key = 'c8v2j8w9e0r1t3y5u7i9o1p3a5s7d9f1g3h5j7k9l1z3x5c7v9b1n3m5'
        code = (
            'import os; os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"; import django; django.setup(); '
            'from django.conf import settings; '
            'print(f"{settings.SESSION_COOKIE_SECURE}|{settings.CSRF_COOKIE_SECURE}|{settings.SECURE_HSTS_SECONDS}|{settings.SECURE_SSL_REDIRECT}")'
        )

        # 1. Production defaults (DEBUG=False)
        prod_env = os.environ.copy()
        prod_env['DEBUG'] = 'False'
        prod_env['SECRET_KEY'] = valid_key
        prod_env['ALLOWED_HOSTS'] = 'smartshop.example.com'
        for k in ['SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS', 'SECURE_SSL_REDIRECT']:
            prod_env.pop(k, None)

        res_prod = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=prod_env)
        self.assertEqual(res_prod.returncode, 0)
        self.assertEqual(res_prod.stdout.strip(), 'True|True|31536000|True')

        # 2. Development defaults (DEBUG=True)
        dev_env = os.environ.copy()
        dev_env['DEBUG'] = 'True'
        dev_env['SECRET_KEY'] = valid_key
        dev_env['ALLOWED_HOSTS'] = 'localhost'
        for k in ['SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS', 'SECURE_SSL_REDIRECT']:
            dev_env.pop(k, None)

        res_dev = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=dev_env)
        self.assertEqual(res_dev.returncode, 0)
        self.assertEqual(res_dev.stdout.strip(), 'False|False|0|False')

    def test_current_settings_security_headers_structure(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, 'X_FRAME_OPTIONS'))
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertTrue(hasattr(settings, 'SECURE_CONTENT_TYPE_NOSNIFF'))
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(hasattr(settings, 'SECURE_BROWSER_XSS_FILTER'))
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)

    def test_logging_configuration(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, 'LOGGING'))
        logging_conf = settings.LOGGING
        self.assertEqual(logging_conf['version'], 1)
        self.assertIn('verbose', logging_conf['formatters'])
        self.assertIn('simple', logging_conf['formatters'])
        self.assertIn('console', logging_conf['handlers'])
        self.assertIn('file', logging_conf['handlers'])
        self.assertIn('django', logging_conf['loggers'])
        self.assertIn('django.request', logging_conf['loggers'])
        self.assertIn('django.security', logging_conf['loggers'])
        self.assertIn('apps', logging_conf['loggers'])
        # File handler uses RotatingFileHandler with 10MB maxBytes and 5 backups
        file_handler = logging_conf['handlers']['file']
        self.assertEqual(file_handler['class'], 'logging.handlers.RotatingFileHandler')
        self.assertEqual(file_handler['maxBytes'], 10 * 1024 * 1024)
        self.assertEqual(file_handler['backupCount'], 5)

    def test_production_check_deploy_passes_cleanly(self):
        import subprocess
        import sys

        env = os.environ.copy()
        env['DEBUG'] = 'False'
        env['SECRET_KEY'] = 'c8v2j8w9e0r1t3y5u7i9o1p3a5s7d9f1g3h5j7k9l1z3x5c7v9b1n3m5'
        env['ALLOWED_HOSTS'] = 'smartshop.example.com'
        env['SECURE_SSL_REDIRECT'] = 'True'

        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('System check identified no issues (0 silenced).', result.stdout)

    def test_production_check_deploy_flags_insecure_defaults(self):
        """DEBUG=True emits deployment warnings during check --deploy."""
        import subprocess
        import sys

        env = os.environ.copy()
        env['DEBUG'] = 'True'
        env['SECRET_KEY'] = 'insecure-key'
        env['ALLOWED_HOSTS'] = 'localhost'

        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('security.W018', result.stderr + result.stdout)


class AccountPortalAndLoginViewTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='cust_user',
            email='cust_user@example.com',
            password='TestPassword123!',
            first_name='Customer',
            last_name='Tester',
            role='CUSTOMER',
        )
        self.cashier = User.objects.create_user(
            username='cashier_user',
            email='cashier_user@example.com',
            password='TestPassword123!',
            first_name='Cashier',
            last_name='Tester',
            role='CASHIER',
        )
        self.manager = User.objects.create_user(
            username='manager_user',
            email='manager_user@example.com',
            password='TestPassword123!',
            first_name='Manager',
            last_name='Tester',
            role='MANAGER',
        )
        self.owner = User.objects.create_user(
            username='owner_user',
            email='owner_user@example.com',
            password='TestPassword123!',
            first_name='Owner',
            last_name='Tester',
            role='OWNER',
        )
        self.staff = User.objects.create_user(
            username='staff_user',
            email='staff_user@example.com',
            password='TestPassword123!',
            first_name='Staff',
            last_name='Tester',
            role='STAFF',
        )

    def test_standard_login_succeeds_without_role_parameter(self):
        """Standard login authenticates without any role field in POST payload."""
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': 'cust_user@example.com', 'password': 'TestPassword123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/customer/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.customer.id)

    def test_customer_login_redirects_to_customer_dashboard(self):
        """Customer signing in at /accounts/login/ is routed to /customer/."""
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.username, 'password': 'TestPassword123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/customer/')

    def test_staff_member_login_at_accounts_login_redirects_to_dashboard(self):
        """Staff roles signing in at /accounts/login/ are redirected to /dashboard/."""
        for user in [self.owner, self.manager, self.cashier, self.staff]:
            self.client.logout()
            response = self.client.post(
                reverse('accounts:login'),
                {'identifier': user.email, 'password': 'TestPassword123!'},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/dashboard/')
            self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_staff_member_login_at_staff_portal_succeeds(self):
        """Staff roles signing in at /accounts/portal/login/ succeed and redirect to /dashboard/."""
        for user in [self.owner, self.manager, self.cashier, self.staff]:
            self.client.logout()
            response = self.client.post(
                reverse('accounts:staff_login'),
                {'identifier': user.email, 'password': 'TestPassword123!'},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/dashboard/')
            self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_customer_login_at_staff_portal_is_blocked(self):
        """Customer attempting to log in at /accounts/portal/login/ is rejected with 403."""
        response = self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': self.customer.email, 'password': 'TestPassword123!'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(
            response,
            'Access denied: Customer accounts cannot sign in through the Staff Portal.',
            status_code=403,
        )

    def test_customer_login_at_staff_portal_json_is_rejected(self):
        """Customer attempting JSON login at staff portal receives 403 JSON error."""
        response = self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': self.customer.email, 'password': 'TestPassword123!'},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Access denied: Customer accounts cannot sign in through the Staff Portal.', data['message'])
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_staff_login_json_succeeds(self):
        """Staff login via JSON returns 200 with redirect_url=/dashboard/."""
        response = self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': self.cashier.email, 'password': 'TestPassword123!'},
            HTTP_ACCEPT='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], '/dashboard/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.cashier.id)

    def test_templates_rendered_correctly(self):
        """GET /accounts/login/ and GET /accounts/portal/login/ render correct templates."""
        login_resp = self.client.get(reverse('accounts:login'))
        self.assertEqual(login_resp.status_code, 200)
        self.assertTemplateUsed(login_resp, 'accounts/login.html')
        self.assertContains(login_resp, 'Staff Login')

        staff_resp = self.client.get(reverse('accounts:staff_login'))
        self.assertEqual(staff_resp.status_code, 200)
        self.assertTemplateUsed(staff_resp, 'accounts/staff_login.html')
        self.assertContains(staff_resp, 'Staff &amp; Terminal Access')
        self.assertContains(staff_resp, 'Customer Login')

    def test_login_invalid_credentials_renders_error(self):
        """Invalid credentials on customer and staff logins re-render template with status 401."""
        login_resp = self.client.post(
            reverse('accounts:login'),
            {'identifier': 'cust_user@example.com', 'password': 'WrongPassword'},
        )
        self.assertEqual(login_resp.status_code, 401)
        self.assertTemplateUsed(login_resp, 'accounts/login.html')
        self.assertContains(login_resp, 'Invalid credentials or inactive account.', status_code=401)

        staff_resp = self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': 'cashier_user@example.com', 'password': 'WrongPassword'},
        )
        self.assertEqual(staff_resp.status_code, 401)
        self.assertTemplateUsed(staff_resp, 'accounts/staff_login.html')
        self.assertContains(staff_resp, 'Invalid credentials or inactive account.', status_code=401)

    def test_activity_log_recorded_on_successful_logins(self):
        """ActivityLog records SYSTEM login events on both customer and staff portal logins."""
        from apps.activity_logs.models import ActivityLog

        # Customer login audit
        self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.email, 'password': 'TestPassword123!'},
        )
        cust_log = ActivityLog.objects.filter(actor=self.customer, action_type='SYSTEM').order_by('-id').first()
        self.assertIsNotNone(cust_log)
        self.assertEqual(cust_log.action_label, 'User Signed In')
        self.assertEqual(cust_log.metadata.get('portal'), 'customer_login')

        # Staff login audit
        self.client.logout()
        self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': self.manager.email, 'password': 'TestPassword123!'},
        )
        staff_log = ActivityLog.objects.filter(actor=self.manager, action_type='SYSTEM').order_by('-id').first()
        self.assertIsNotNone(staff_log)
        self.assertEqual(staff_log.action_label, 'Staff Signed In')
        self.assertEqual(staff_log.metadata.get('portal'), 'staff_portal')

    def test_public_registration_html_redirects_to_customer(self):
        """Standard form POST to /accounts/register/ creates CUSTOMER and redirects to /customer/."""
        from apps.accounts.models import CustomerProfile

        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Jane',
                'last_name': 'Shopper',
                'email': 'janeshopper@example.com',
                'phone': '+2348011112222',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
                'terms': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/customer/')

        new_user = User.objects.get(email='janeshopper@example.com')
        self.assertEqual(new_user.role, User.Role.CUSTOMER)
        self.assertTrue(new_user.is_active)
        self.assertTrue(CustomerProfile.objects.filter(user=new_user).exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), new_user.id)

    def test_public_registration_ignores_privileged_roles_in_payload(self):
        """Submitting role='OWNER' or role='STAFF' in registration payload is ignored, enforcing CUSTOMER."""
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Hacker',
                'last_name': 'Attempt',
                'email': 'hacker@example.com',
                'phone': '+2348099998888',
                'role': 'OWNER',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
                'terms': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/customer/')

        user = User.objects.get(email='hacker@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(User.objects.filter(email='hacker@example.com', role='OWNER').exists())

    def test_public_registration_get_renders_template_without_role_selector(self):
        """GET /accounts/register/ renders template with no role/account type selector dropdown."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')
        self.assertNotContains(response, 'id="accountRole"')
        self.assertNotContains(response, 'name="role"')
        self.assertNotContains(response, 'Account type')
        self.assertContains(response, 'First name')
        self.assertContains(response, 'Last name')
        self.assertContains(response, 'Email address')
        self.assertContains(response, 'Phone number')
        self.assertContains(response, 'Password')
        self.assertContains(response, 'Confirm password')

    def test_public_registration_validation_error_renders_form(self):
        """Form validation failure (e.g. mismatched passwords) re-renders register.html with status 400."""
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Mismatch',
                'last_name': 'Tester',
                'email': 'mismatch@example.com',
                'phone': '+2348011113333',
                'password': 'StrongPass123!',
                'confirm_password': 'DifferentPassword456!',
                'terms': 'on',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'accounts/register.html')
        self.assertContains(response, 'Passwords do not match.', status_code=400)
        self.assertFalse(User.objects.filter(email='mismatch@example.com').exists())


class RoleBasedEntryRoutingAndRedirectTests(TestCase):
    """Test suite for role-based entry routing and post-login redirection."""

    def setUp(self):
        self.password = 'SecurePass123!'
        self.customer = User.objects.create_user(
            username='cust_redirect_user',
            email='cust_redirect@example.com',
            password=self.password,
            first_name='Customer',
            last_name='Redirect',
            role='CUSTOMER',
        )
        self.cashier = User.objects.create_user(
            username='cashier_redirect_user',
            email='cashier_redirect@example.com',
            password=self.password,
            first_name='Cashier',
            last_name='Redirect',
            role='CASHIER',
        )
        self.manager = User.objects.create_user(
            username='manager_redirect_user',
            email='manager_redirect@example.com',
            password=self.password,
            first_name='Manager',
            last_name='Redirect',
            role='MANAGER',
        )
        self.owner = User.objects.create_user(
            username='owner_redirect_user',
            email='owner_redirect@example.com',
            password=self.password,
            first_name='Owner',
            last_name='Redirect',
            role='OWNER',
        )

    def test_get_role_redirect_url_anonymous(self):
        from apps.accounts.services import get_role_redirect_url
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(get_role_redirect_url(None), '/customer/products/')
        self.assertEqual(get_role_redirect_url(AnonymousUser()), '/customer/products/')

    def test_get_role_redirect_url_customer(self):
        from apps.accounts.services import get_role_redirect_url

        self.assertEqual(get_role_redirect_url(self.customer), '/customer/products/')

    def test_get_role_redirect_url_cashier(self):
        from apps.accounts.services import get_role_redirect_url

        self.assertEqual(get_role_redirect_url(self.cashier), '/sales/pos/')

    def test_get_role_redirect_url_manager(self):
        from apps.accounts.services import get_role_redirect_url

        self.assertEqual(get_role_redirect_url(self.manager), '/reports/')

    def test_get_role_redirect_url_owner_and_admin(self):
        from apps.accounts.services import get_role_redirect_url

        self.assertEqual(get_role_redirect_url(self.owner), '/reports/')

        admin_user = User(username='admin_test', role='ADMIN')
        self.assertEqual(get_role_redirect_url(admin_user), '/reports/')

    def test_root_entry_redirects_anonymous_to_storefront(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/customer/products/')

    def test_root_entry_redirects_customer_to_storefront(self):
        self.client.force_login(self.customer)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/customer/products/')

    def test_root_entry_redirects_cashier_to_pos(self):
        self.client.force_login(self.cashier)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/sales/pos/')

    def test_root_entry_redirects_manager_to_reports(self):
        self.client.force_login(self.manager)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/reports/')

    def test_root_entry_redirects_owner_to_reports(self):
        self.client.force_login(self.owner)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/reports/')

    def test_customer_login_redirects_to_products(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.customer.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/customer/products/')

    def test_cashier_login_redirects_to_pos(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.cashier.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/sales/pos/')

    def test_manager_login_redirects_to_reports(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.manager.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/reports/')

    def test_owner_login_redirects_to_reports(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'identifier': self.owner.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/reports/')

    def test_login_preserves_safe_next_url_for_staff(self):
        response = self.client.post(
            f"{reverse('accounts:login')}?next=/sales/history/",
            {'identifier': self.cashier.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/sales/history/')

    def test_customer_login_blocks_unsafe_internal_dashboard_next(self):
        response = self.client.post(
            f"{reverse('accounts:login')}?next=/dashboard/",
            {'identifier': self.customer.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/customer/products/')
