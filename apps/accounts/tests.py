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
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email='public@example.com')
        self.assertEqual(user.role, 'CUSTOMER')
        self.assertTrue(response.json()['success'])

    def test_staff_registration_is_rejected(self):
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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='staff@example.com').exists())

    def test_cashier_registration_is_rejected(self):
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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='cashier@example.com').exists())

    def test_manager_registration_is_rejected(self):
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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='manager@example.com').exists())

    def test_owner_registration_is_rejected(self):
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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='owner2@example.com').exists())

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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='privileged@example.com').exists())
        self.assertFalse(User.objects.filter(email='privileged@example.com', role='STAFF').exists())

    def test_registration_without_role_is_rejected(self):
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
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='missingrole@example.com').exists())

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
