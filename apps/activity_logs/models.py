from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class ActivityLog(models.Model):
    """Historical audit record for the MADAM HY business domain."""

    class ActionType(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        UPDATED = 'UPDATED', 'Updated'
        DELETED = 'DELETED', 'Deleted'
        VIEWED = 'VIEWED', 'Viewed'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        PAYMENT = 'PAYMENT', 'Payment'
        INVENTORY = 'INVENTORY', 'Inventory'
        SYSTEM = 'SYSTEM', 'System'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        db_index=True,
        help_text='User who initiated the action. May be null for system events.',
    )
    action_type = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        db_index=True,
        help_text='Type of action recorded in the log.',
    )
    action_label = models.CharField(
        max_length=200,
        help_text='Short summary of the action that took place.',
    )
    description = models.TextField(
        help_text='Detailed information explaining what happened.',
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_log_records',
        help_text='Optional content type of the related business record.',
    )
    object_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Optional primary key of the related business record.',
    )
    related_object = GenericForeignKey('content_type', 'object_id')
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional structured information, such as old/new values or references.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
        indexes = [
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        actor_name = self.actor.get_full_name() if self.actor else 'System'
        return f'{actor_name} - {self.action_label}'

    def clean(self):
        super().clean()
        if not self.action_label or not self.action_label.strip():
            raise ValidationError({'action_label': 'Action label is required.'})
        if not self.description or not self.description.strip():
            raise ValidationError({'description': 'Description is required.'})
        if self.metadata is None:
            self.metadata = {}

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.metadata is None:
            self.metadata = {}
        super().save(*args, **kwargs)

    @property
    def content_object(self):
        return self.related_object


class ActivityLogQuerySet(models.QuerySet):
    def for_actor(self, user):
        return self.filter(actor=user)

    def for_action(self, action_type):
        return self.filter(action_type=action_type)

    def latest(self):
        return self.order_by('-created_at', '-id')
