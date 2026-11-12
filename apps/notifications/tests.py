from datetime import timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.credits.models import CreditAccount
from apps.expenses.models import Expense
from apps.inventory.models import InventoryItem
from apps.notifications.models import Notification
from apps.notifications.services import (
    NotificationService,
    create_notification,
    mark_all_notifications_as_read,
    unread_notifications_count,
)
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product, ProductCategory
from apps.requests.models import Request


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notify_user',
            email='notify_user@example.com',
            password='StrongPass123!',
            first_name='Notify',
            last_name='User',
            role='CUSTOMER',
        )
        self.staff = User.objects.create_user(
            username='notify_staff',
            email='notify_staff@example.com',
            password='StrongPass123!',
            first_name='Notify',
            last_name='Staff',
            role='MANAGER',
        )
        self.category = ProductCategory.objects.create(
            name='Office',
            slug='office',
            description='Office supply items',
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Notebook',
            slug='notebook',
            sku='NB-001',
            description='Notebook',
            selling_price=Decimal('25.00'),
            cost_price=Decimal('12.00'),
            reorder_level=3,
        )
        self.inventory = InventoryItem.objects.create(product=self.product, quantity=1)

    def test_notification_creation(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.ORDER,
            title='New order',
            message='Order received',
            priority=Notification.Priority.HIGH,
            action_url='/orders/1/',
        )
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.title, 'New order')
        self.assertFalse(notification.is_read)

    def test_recipient_relationship(self):
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Welcome',
            message='Welcome to MADAM HY',
        )
        self.assertEqual(self.user.notifications.count(), 1)

    def test_notification_types(self):
        self.assertIn(Notification.NotificationType.ORDER, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.PAYMENT, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.CREDIT, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.REQUEST, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.INVENTORY, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.EXPENSE, [choice[0] for choice in Notification.NotificationType.choices])
        self.assertIn(Notification.NotificationType.SYSTEM, [choice[0] for choice in Notification.NotificationType.choices])

    def test_priority_choices(self):
        self.assertIn(Notification.Priority.LOW, [choice[0] for choice in Notification.Priority.choices])
        self.assertIn(Notification.Priority.NORMAL, [choice[0] for choice in Notification.Priority.choices])
        self.assertIn(Notification.Priority.HIGH, [choice[0] for choice in Notification.Priority.choices])
        self.assertIn(Notification.Priority.URGENT, [choice[0] for choice in Notification.Priority.choices])

    def test_default_unread_state(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='System alert',
            message='A system alert was raised.',
        )
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_mark_as_read(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Read me',
            message='Read me now.',
        )
        notification.mark_as_read()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_as_unread(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Unread me',
            message='Unread me now.',
        )
        notification.mark_as_read()
        notification.mark_as_unread()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

    def test_mark_all_as_read(self):
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='One',
            message='One',
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Two',
            message='Two',
        )
        mark_all_notifications_as_read(self.user)
        self.assertEqual(self.user.notifications.filter(is_read=True).count(), 2)
        self.assertEqual(unread_notifications_count(self.user), 0)

    def test_unread_count(self):
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Unread 1',
            message='Unread 1',
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Unread 2',
            message='Unread 2',
        )
        Notification.objects.create(
            recipient=self.staff,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Other user',
            message='Other user',
        )
        self.assertEqual(unread_notifications_count(self.user), 2)

    def test_newest_first_ordering(self):
        old = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='Old',
            message='Old',
        )
        old.created_at = timezone.now() - timedelta(days=1)
        old.save(update_fields=['created_at'])

        new = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.SYSTEM,
            title='New',
            message='New',
        )
        self.assertEqual(list(self.user.notifications.all()[:1]), [new])

    def test_related_object_reference(self):
        order = Order.objects.create(
            order_number='ORD-1001',
            customer=self.user,
            created_by=self.staff,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('40.00'),
            subtotal=Decimal('40.00'),
        )
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.ORDER,
            title='Order update',
            message='Your order changed status',
            related_object=order,
            action_url='/orders/ORD-1001/',
        )
        self.assertEqual(notification.related_object, order)

    def test_related_object_deletion_does_not_destroy_notification(self):
        order = Order.objects.create(
            order_number='ORD-1002',
            customer=self.user,
            created_by=self.staff,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('50.00'),
            subtotal=Decimal('50.00'),
        )
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.ORDER,
            title='Saved order notification',
            message='This should persist even if the order is deleted.',
            related_object=order,
        )
        order.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.related_object)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

    def test_action_url(self):
        notification = Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.REQUEST,
            title='Request update',
            message='Your request was reviewed.',
            action_url='/requests/42/',
        )
        self.assertEqual(notification.action_url, '/requests/42/')

    def test_notification_service_helper(self):
        notification = create_notification(
            recipient=self.user,
            notification_type=Notification.NotificationType.INVENTORY,
            title='Low stock',
            message='Notebook is running low',
            priority=Notification.Priority.HIGH,
            related_object=self.inventory,
            action_url='/inventory/',
        )
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.title, 'Low stock')
        self.assertEqual(notification.priority, Notification.Priority.HIGH)

    def test_invalid_recipient_handling(self):
        with self.assertRaises(ValueError):
            create_notification(
                recipient=None,
                notification_type=Notification.NotificationType.SYSTEM,
                title='Missing recipient',
                message='No recipient',
            )

    def test_database_indexes_and_constraints(self):
        self.assertTrue(Notification._meta.indexes)
        self.assertIsNotNone(Notification._meta.get_field('recipient'))
        self.assertIsNotNone(Notification._meta.get_field('notification_type'))
        self.assertIsNotNone(Notification._meta.get_field('is_read'))

    def test_django_system_checks(self):
        call_command('check')

    def test_notification_operations_do_not_modify_orders(self):
        order = Order.objects.create(
            order_number='ORD-1003',
            customer=self.user,
            created_by=self.staff,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('55.00'),
            subtotal=Decimal('55.00'),
        )
        original_total = order.total
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.ORDER,
            title='Order note',
            message='Order note created',
            related_object=order,
        ).mark_as_read()
        order.refresh_from_db()
        self.assertEqual(order.total, original_total)

    def test_notification_operations_do_not_modify_payments(self):
        order = Order.objects.create(
            order_number='ORD-1004',
            customer=self.user,
            created_by=self.staff,
            payment_method=Order.PaymentMethod.CASH,
            total=Decimal('60.00'),
            subtotal=Decimal('60.00'),
        )
        payment = Payment.objects.create(
            payment_reference='PAY-1001',
            customer=self.user,
            cashier=self.staff,
            order=order,
            amount=Decimal('60.00'),
            payment_method=Payment.PaymentMethod.CASH,
            payment_status=Payment.PaymentStatus.COMPLETED,
        )
        original_amount = payment.amount
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.PAYMENT,
            title='Payment note',
            message='Payment note created',
            related_object=payment,
        ).mark_as_read()
        payment.refresh_from_db()
        self.assertEqual(payment.amount, original_amount)

    def test_notification_operations_do_not_modify_credits(self):
        credit_account = CreditAccount.objects.create(
            customer=self.user,
            credit_limit=Decimal('300.00'),
            outstanding_balance=Decimal('80.00'),
            status=CreditAccount.Status.ACTIVE,
            approved_by=self.staff,
        )
        original_balance = credit_account.outstanding_balance
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.CREDIT,
            title='Credit note',
            message='Credit note created',
            related_object=credit_account,
        ).mark_as_read()
        credit_account.refresh_from_db()
        self.assertEqual(credit_account.outstanding_balance, original_balance)

    def test_notification_operations_do_not_modify_requests(self):
        request = Request.objects.create(
            request_number='REQ-1001',
            customer=self.user,
            request_type=Request.RequestType.GENERAL,
            title='Need help',
            description='I need help.',
            status=Request.Status.PENDING,
            priority=Request.Priority.NORMAL,
        )
        original_title = request.title
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.REQUEST,
            title='Request note',
            message='Request note created',
            related_object=request,
        ).mark_as_read()
        request.refresh_from_db()
        self.assertEqual(request.title, original_title)

    def test_notification_operations_do_not_modify_inventory(self):
        original_quantity = self.inventory.quantity
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.INVENTORY,
            title='Inventory note',
            message='Inventory note created',
            related_object=self.inventory,
        ).mark_as_read()
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, original_quantity)

    def test_notification_operations_do_not_modify_expenses(self):
        expense = Expense.objects.create(
            expense_reference='EXP-1001',
            category=Expense.Category.OTHER,
            description='Office supply',
            amount=Decimal('40.00'),
            expense_date=timezone.now().date(),
            vendor='Office Shop',
            payment_method=Expense.PaymentMethod.CASH,
            payment_reference='PAY-EXP-1001',
            recorded_by=self.staff,
        )
        original_amount = expense.amount
        Notification.objects.create(
            recipient=self.user,
            notification_type=Notification.NotificationType.EXPENSE,
            title='Expense note',
            message='Expense note created',
            related_object=expense,
        ).mark_as_read()
        expense.refresh_from_db()
        self.assertEqual(expense.amount, original_amount)


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='service_user1',
            email='service_user1@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )
        self.user2 = User.objects.create_user(
            username='service_user2',
            email='service_user2@example.com',
            password='StrongPass123!',
            role='CUSTOMER',
        )

    def test_service_create_notification(self):
        notif = NotificationService.create_notification(
            recipient=self.user1,
            notification_type='ORDER',
            title='Order received',
            message='Your order is confirmed.',
            priority='HIGH',
            action_url='/orders/ORD-001/',
        )
        self.assertEqual(notif.recipient, self.user1)
        self.assertEqual(notif.notification_type, 'ORDER')
        self.assertEqual(notif.priority, 'HIGH')
        self.assertFalse(notif.is_read)

    def test_service_get_user_notifications_filtering(self):
        n1 = NotificationService.create_notification(self.user1, 'ORDER', 'Order 1', 'Shipped', priority='NORMAL')
        n2 = NotificationService.create_notification(self.user1, 'PAYMENT', 'Payment 1', 'Paid', priority='HIGH')
        n3 = NotificationService.create_notification(self.user1, 'SYSTEM', 'Alert', 'Maintenance', priority='URGENT')
        n3.mark_as_read()
        NotificationService.create_notification(self.user2, 'ORDER', 'Order User 2', 'Shipped', priority='NORMAL')

        user1_all = NotificationService.get_user_notifications(self.user1)
        self.assertEqual(user1_all.count(), 3)

        unread = NotificationService.get_user_notifications(self.user1, is_read=False)
        self.assertEqual(unread.count(), 2)

        read = NotificationService.get_user_notifications(self.user1, is_read=True)
        self.assertEqual(read.count(), 1)
        self.assertEqual(read.first(), n3)

        order_type = NotificationService.get_user_notifications(self.user1, notification_type='ORDER')
        self.assertEqual(order_type.count(), 1)
        self.assertEqual(order_type.first(), n1)

        high_prio = NotificationService.get_user_notifications(self.user1, priority='HIGH')
        self.assertEqual(high_prio.count(), 1)
        self.assertEqual(high_prio.first(), n2)

        search_res = NotificationService.get_user_notifications(self.user1, search='Maintenance')
        self.assertEqual(search_res.count(), 1)
        self.assertEqual(search_res.first(), n3)

    def test_service_metrics(self):
        NotificationService.create_notification(self.user1, 'ORDER', 'O1', 'M1', priority='NORMAL')
        NotificationService.create_notification(self.user1, 'ORDER', 'O2', 'M2', priority='URGENT')
        n3 = NotificationService.create_notification(self.user1, 'ORDER', 'O3', 'M3', priority='LOW')
        n3.mark_as_read()

        metrics = NotificationService.get_notification_metrics(self.user1)
        self.assertEqual(metrics['total'], 3)
        self.assertEqual(metrics['unread'], 2)
        self.assertEqual(metrics['read'], 1)
        self.assertEqual(metrics['urgent_unread'], 1)

    def test_service_mark_as_read_isolation(self):
        n_user2 = NotificationService.create_notification(self.user2, 'ORDER', 'User 2', 'Message')
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            NotificationService.mark_as_read(n_user2.id, user=self.user1)

    def test_service_mark_all_as_read(self):
        NotificationService.create_notification(self.user1, 'ORDER', 'O1', 'M1')
        NotificationService.create_notification(self.user1, 'ORDER', 'O2', 'M2')
        NotificationService.create_notification(self.user2, 'ORDER', 'O3', 'M3')

        updated = NotificationService.mark_all_as_read(self.user1)
        self.assertEqual(updated, 2)
        self.assertEqual(NotificationService.get_unread_count(self.user1), 0)
        self.assertEqual(NotificationService.get_unread_count(self.user2), 1)

    def test_service_serialize_notification(self):
        n = NotificationService.create_notification(self.user1, 'ORDER', 'Title', 'Msg', priority='HIGH')
        data = NotificationService.serialize_notification(n)
        self.assertEqual(data['id'], n.id)
        self.assertEqual(data['title'], 'Title')
        self.assertEqual(data['priority'], 'HIGH')
        self.assertFalse(data['is_read'])
        self.assertIn('created_at_display', data)


class NotificationViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='view_user',
            email='view_user@example.com',
            password='StrongPass123!',
            first_name='View',
            last_name='User',
            role='CUSTOMER',
        )
        self.other_user = User.objects.create_user(
            username='other_user',
            email='other_user@example.com',
            password='StrongPass123!',
            first_name='Other',
            last_name='User',
            role='CUSTOMER',
        )
        self.n1 = NotificationService.create_notification(
            self.user, 'ORDER', 'Order Placed', 'Your order was received.', priority='NORMAL'
        )
        self.n2 = NotificationService.create_notification(
            self.user, 'PAYMENT', 'Payment Received', 'Receipt for payment.', priority='HIGH'
        )
        self.other_n = NotificationService.create_notification(
            self.other_user, 'CREDIT', 'Credit Alert', 'Credit limit updated.', priority='URGENT'
        )

    def test_inbox_requires_authentication(self):
        res_html = self.client.get('/notifications/')
        self.assertEqual(res_html.status_code, 302)
        self.assertIn('/accounts/login/', res_html.url)

        res_json = self.client.get('/notifications/', HTTP_ACCEPT='application/json')
        self.assertEqual(res_json.status_code, 401)
        self.assertFalse(res_json.json()['success'])

    def test_inbox_html_rendering(self):
        self.client.force_login(self.user)
        res = self.client.get('/notifications/')
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'notifications/notifications.html')
        self.assertContains(res, 'Notifications Center')
        self.assertContains(res, 'Order Placed')
        self.assertContains(res, 'Payment Received')
        self.assertNotContains(res, 'Credit Alert')

    def test_inbox_json_api(self):
        self.client.force_login(self.user)
        res = self.client.get('/notifications/?format=json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        notifs = data['data']['notifications']
        self.assertEqual(len(notifs), 2)
        titles = [n['title'] for n in notifs]
        self.assertIn('Order Placed', titles)
        self.assertIn('Payment Received', titles)
        self.assertNotIn('Credit Alert', titles)
        self.assertEqual(data['data']['metrics']['unread'], 2)
        self.assertEqual(data['unread_count'], 2)

    def test_inbox_filtering(self):
        self.client.force_login(self.user)
        res_order = self.client.get('/notifications/?type=ORDER&format=json')
        self.assertEqual(res_order.status_code, 200)
        data = res_order.json()['data']['notifications']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Order Placed')

        res_prio = self.client.get('/notifications/?priority=HIGH&format=json')
        self.assertEqual(res_prio.status_code, 200)
        data = res_prio.json()['data']['notifications']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Payment Received')

        res_search = self.client.get('/notifications/?q=Receipt&format=json')
        self.assertEqual(res_search.status_code, 200)
        data = res_search.json()['data']['notifications']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Payment Received')

    def test_unread_count_api(self):
        res_anon = self.client.get('/notifications/unread-count/')
        self.assertEqual(res_anon.status_code, 401)

        self.client.force_login(self.user)
        res = self.client.get('/notifications/unread-count/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['unread_count'], 2)
        self.assertEqual(data['data']['unread_count'], 2)

    def test_mark_single_as_read(self):
        self.client.force_login(self.user)
        res = self.client.post(f'/notifications/{self.n1.id}/read/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['data']['notification']['is_read'])
        self.assertEqual(data['unread_count'], 1)

        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)
        self.assertIsNotNone(self.n1.read_at)
        self.assertEqual(NotificationService.get_unread_count(self.user), 1)

    def test_mark_single_as_read_isolation(self):
        self.client.force_login(self.user)
        res = self.client.post(f'/notifications/{self.other_n.id}/read/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()['success'])
        self.assertIn('Permission denied', res.json()['message'])

        self.other_n.refresh_from_db()
        self.assertFalse(self.other_n.is_read)

    def test_mark_single_as_read_not_found(self):
        self.client.force_login(self.user)
        res = self.client.post('/notifications/99999/read/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.json()['success'])

    def test_mark_single_as_read_invalid_id(self):
        self.client.force_login(self.user)
        res = self.client.post('/notifications/invalid-id/read/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()['success'])

    def test_mark_single_as_read_method_not_allowed(self):
        self.client.force_login(self.user)
        res = self.client.get(f'/notifications/{self.n1.id}/read/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 405)

    def test_mark_single_as_unread(self):
        self.n1.mark_as_read()
        self.client.force_login(self.user)
        res = self.client.post(f'/notifications/{self.n1.id}/unread/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['data']['notification']['is_read'])
        self.n1.refresh_from_db()
        self.assertFalse(self.n1.is_read)

    def test_mark_all_as_read(self):
        self.client.force_login(self.user)
        res = self.client.post('/notifications/read-all/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['marked_count'], 2)
        self.assertEqual(data['unread_count'], 0)

        self.assertEqual(NotificationService.get_unread_count(self.user), 0)
        self.assertEqual(NotificationService.get_unread_count(self.other_user), 1)

    def test_mark_all_as_read_method_not_allowed(self):
        self.client.force_login(self.user)
        res = self.client.get('/notifications/read-all/', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 405)
