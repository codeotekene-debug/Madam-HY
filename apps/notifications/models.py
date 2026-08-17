from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """In-app notification record that remains lightweight and independent from business logic."""

    class NotificationType(models.TextChoices):
        ORDER = 'ORDER', 'Order'
        PAYMENT = 'PAYMENT', 'Payment'
        CREDIT = 'CREDIT', 'Credit'
        REQUEST = 'REQUEST', 'Request'
        INVENTORY = 'INVENTORY', 'Inventory'
        EXPENSE = 'EXPENSE', 'Expense'
        SYSTEM = 'SYSTEM', 'System'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        NORMAL = 'NORMAL', 'Normal'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True,
        help_text='User who receives the notification.',
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        db_index=True,
        help_text='Category of activity being reported.',
    )
    title = models.CharField(
        max_length=200,
        help_text='Short summary of the notification.',
    )
    message = models.TextField(
        help_text='Detailed message shown to the recipient.',
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
        help_text='Importance level for the notification.',
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether the user has read the notification.',
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the notification was marked as read.',
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_content',
        help_text='Optional content type of the related business record.',
    )
    object_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional primary key of the related business record.',
    )
    related_object = GenericForeignKey('content_type', 'object_id')
    action_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Optional app-relative URL the user can open.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['notification_type', '-created_at']),
            models.Index(fields=['priority', '-created_at']),
            models.Index(fields=['is_read', '-created_at']),
        ]

    def __str__(self):
        return f'{self.recipient} - {self.title}'

    def clean(self):
        super().clean()
        if self.recipient_id is None:
            raise ValidationError({'recipient': 'Every notification must have a recipient.'})
        if not self.title.strip():
            raise ValidationError({'title': 'Notification title is required.'})
        if not self.message.strip():
            raise ValidationError({'message': 'Notification message is required.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_as_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at', 'updated_at'])
        return self

    def mark_as_unread(self):
        self.is_read = False
        self.read_at = None
        self.save(update_fields=['is_read', 'read_at', 'updated_at'])
        return self


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(is_read=False)

    def read(self):
        return self.filter(is_read=True)
