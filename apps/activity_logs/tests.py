from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
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
