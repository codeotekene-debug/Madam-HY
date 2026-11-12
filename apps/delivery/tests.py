import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.delivery.models import Delivery, DeliveryAssignment, DeliveryZone, RiderProfile
from apps.delivery.services import DeliveryService
from apps.orders.models import Order


class RiderAndDeliveryFoundationTests(TestCase):
    def setUp(self):
        self.rider = User.objects.create_user(
            username='phase2_rider',
            email='phase2-rider@example.com',
            password='SecurePass123!',
            first_name='Phase',
            last_name='Rider',
            role=User.Role.RIDER,
        )
        self.manager = User.objects.create_user(
            username='phase2_manager',
            email='phase2-manager@example.com',
            password='SecurePass123!',
            role=User.Role.MANAGER,
        )
        self.customer = User.objects.create_user(
            username='phase2_customer',
            email='phase2-customer@example.com',
            password='SecurePass123!',
            role=User.Role.CUSTOMER,
        )
        self.order = Order.objects.create(
            order_number='MH-ORD-PHASE2',
            customer=self.customer,
            payment_method=Order.PaymentMethod.CASH,
            delivery_address='12 Test Street, Lagos',
        )
        self.delivery = Delivery.objects.create(
            order=self.order,
            tracking_number='MH-DEL-PHASE2',
            delivery_address=self.order.delivery_address,
        )

    def test_rider_role_redirects_to_rider_dashboard(self):
        from apps.accounts.services import get_role_redirect_url

        self.assertEqual(User.Role.RIDER, 'RIDER')
        self.assertEqual(get_role_redirect_url(self.rider), '/rider/')

    def test_rider_can_authenticate_through_staff_portal_and_lands_in_rider_portal(self):
        response = self.client.post(
            reverse('accounts:staff_login'),
            {'identifier': self.rider.email, 'password': 'SecurePass123!'},
        )

        self.assertRedirects(response, '/rider/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.rider.id)

    def test_public_registration_cannot_create_rider_account(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Public',
                'last_name': 'Rider',
                'email': 'public-rider@example.com',
                'phone': '+2348012345678',
                'role': User.Role.RIDER,
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
                'terms': 'on',
            },
        )

        self.assertRedirects(response, '/customer/', fetch_redirect_response=False)
        public_user = User.objects.get(email='public-rider@example.com')
        self.assertEqual(public_user.role, User.Role.CUSTOMER)

    def test_management_can_create_rider_account_with_valid_password(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('delivery:management_create_rider'),
            data=json.dumps({
                'email': 'new-rider@example.com',
                'username': 'new_phase2_rider',
                'first_name': 'New',
                'last_name': 'Rider',
                'password': 'StrongRiderPass123!',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        new_rider = User.objects.get(email='new-rider@example.com')
        self.assertEqual(new_rider.role, User.Role.RIDER)
        self.assertTrue(new_rider.check_password('StrongRiderPass123!'))
        self.assertTrue(RiderProfile.objects.filter(user=new_rider).exists())

    def test_rider_cannot_create_another_rider_account(self):
        self.client.force_login(self.rider)
        response = self.client.post(
            reverse('delivery:management_create_rider'),
            data=json.dumps({'email': 'unauthorized-rider@example.com', 'password': 'StrongRiderPass123!'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email='unauthorized-rider@example.com').exists())

    def test_rider_creation_requires_valid_initial_password(self):
        for payload in (
            {'email': 'missing-password@example.com'},
            {'email': 'weak-password@example.com', 'password': 'short'},
        ):
            with self.subTest(email=payload['email']):
                with self.assertRaises(ValidationError):
                    DeliveryService.create_rider_account(payload, created_by=self.manager)

        self.assertFalse(User.objects.filter(email__endswith='@example.com', role=User.Role.RIDER).exclude(pk=self.rider.pk).exists())

    def test_rider_profile_requires_rider_account(self):
        profile = RiderProfile(user=self.rider)
        profile.full_clean()
        profile.save()
        self.assertEqual(self.rider.rider_profile, profile)

        invalid_profile = RiderProfile(user=self.customer)
        with self.assertRaises(ValidationError):
            invalid_profile.full_clean()

    def test_assignment_records_rider_actor_status_and_time(self):
        assignment = DeliveryAssignment.objects.create(
            delivery=self.delivery,
            rider=self.rider,
            assigned_by=self.manager,
            reason='Assigned for the morning delivery run.',
        )

        self.assertEqual(self.delivery.assignments.get(), assignment)
        self.assertEqual(assignment.status, DeliveryAssignment.AssignmentStatus.ASSIGNED)
        self.assertIsNotNone(assignment.assigned_at)

    def test_assignment_rejects_non_rider_account(self):
        with self.assertRaises(ValidationError):
            DeliveryAssignment.objects.create(
                delivery=self.delivery,
                rider=self.customer,
                assigned_by=self.manager,
            )

    def test_rider_cannot_be_recorded_as_assignment_manager(self):
        with self.assertRaises(ValidationError):
            DeliveryAssignment.objects.create(
                delivery=self.delivery,
                rider=self.rider,
                assigned_by=self.rider,
            )

    def test_delivery_cannot_be_deleted_after_assignment_history_exists(self):
        DeliveryAssignment.objects.create(
            delivery=self.delivery,
            rider=self.rider,
            assigned_by=self.manager,
        )

        with self.assertRaises(ProtectedError):
            self.delivery.delete()

    def test_rider_and_management_pages_render(self):
        self.client.force_login(self.rider)
        self.delivery.rider = self.rider
        self.delivery.save(update_fields=['rider'])
        rider_pages = [
            'rider_dashboard', 'rider_assignments', 'rider_deliveries',
            'rider_delivery_detail', 'rider_active_delivery', 'rider_history',
            'rider_profile', 'rider_notifications',
        ]
        for page in rider_pages:
            kwargs = {'args': [self.delivery.id]} if page == 'rider_delivery_detail' else {}
            self.assertEqual(self.client.get(reverse(f'delivery:{page}', **kwargs)).status_code, 200, page)
        self.client.force_login(self.manager)
        management_home = self.client.get(reverse('delivery:management_dashboard'))
        self.assertContains(management_home, 'href="/deliveries/"')
        self.assertContains(management_home, 'aria-current="page"')
        manager_pages = [
            'management_dashboard', 'management_all', 'management_unassigned',
            'management_active', 'management_completed', 'management_failed',
            'management_detail', 'management_riders', 'management_rider_detail',
            'management_zones', 'management_settings', 'management_reports',
        ]
        for page in manager_pages:
            kwargs = {'args': [self.delivery.id if page == 'management_detail' else self.rider.id]} if page in {'management_detail', 'management_rider_detail'} else {}
            self.assertEqual(self.client.get(reverse(f'delivery:{page}', **kwargs)).status_code, 200, page)

    def test_cashier_cannot_access_delivery_management_or_see_sidebar_link(self):
        cashier = User.objects.create_user(
            username='delivery_cashier',
            email='delivery-cashier@example.com',
            password='SecurePass123!',
            role=User.Role.CASHIER,
        )
        self.client.force_login(cashier)
        response = self.client.get(reverse('delivery:management_dashboard'))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'href="/deliveries/"', response.content)

    def test_failed_otp_attempt_is_persisted(self):
        self.delivery.rider = self.rider
        self.delivery.status = Delivery.DeliveryStatus.IN_TRANSIT
        self.delivery.set_otp('123456')
        self.delivery.save(update_fields=['rider', 'status'])
        result = DeliveryService.verify_delivery_otp(self.delivery, '000000', self.rider)
        self.delivery.refresh_from_db()
        self.assertFalse(result['success'])
        self.assertEqual(self.delivery.otp_attempts, 1)

    def test_rider_cannot_view_another_riders_delivery(self):
        other = User.objects.create_user(
            username='another_rider', email='another-rider@example.com', password='SecurePass123!', role=User.Role.RIDER,
        )
        self.delivery.rider = other
        self.delivery.save(update_fields=['rider'])
        self.client.force_login(self.rider)
        response = self.client.get(reverse('delivery:rider_delivery_detail', args=[self.delivery.id]))
        self.assertEqual(response.status_code, 404)

    def test_dispatch_requires_confirmed_order_and_payment_or_cash_on_delivery(self):
        with self.assertRaises(ValidationError):
            DeliveryService.assign_rider(self.delivery, self.rider, self.manager)

        self.order.status = Order.OrderStatus.CONFIRMED
        self.order.payment_method = Order.PaymentMethod.CARD
        self.order.payment_status = Order.PaymentStatus.PENDING
        self.order.save(update_fields=['status', 'payment_method', 'payment_status', 'updated_at'])
        with self.assertRaises(ValidationError):
            DeliveryService.assign_rider(self.delivery, self.rider, self.manager)

        self.order.payment_method = Order.PaymentMethod.CASH
        self.order.save(update_fields=['payment_method', 'updated_at'])
        assigned = DeliveryService.assign_rider(self.delivery, self.rider, self.manager)
        self.assertEqual(assigned.rider, self.rider)

    def test_confirming_delivery_order_creates_job_without_completing_order(self):
        zone = DeliveryZone.objects.create(name='Test Delivery Area', code='TEST-AREA', fee='500.00')
        self.delivery.delete()
        self.order.delivery_zone = zone
        self.order.delivery_fee = '500.00'
        self.order.total = '500.00'
        self.order.notes = 'Delivery: Delivery | Recipient: Customer'
        self.order.save()
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('orders:status_update', args=[self.order.id]),
            data=json.dumps({'status': Order.OrderStatus.CONFIRMED}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(self.order.delivery.status, Delivery.DeliveryStatus.PENDING_ASSIGNMENT)
        self.assertEqual(self.order.delivery.delivery_fee, Decimal('500.00'))
