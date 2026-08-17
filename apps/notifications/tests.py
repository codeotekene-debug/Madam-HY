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
from apps.notifications.services import create_notification, mark_all_notifications_as_read, unread_notifications_count
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
