from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class ActivityLogQuerySet(models.QuerySet):
    """Custom queryset providing convenience filters for activity log entries."""

    def for_actor(self, user):
        return self.filter(actor=user)

    def for_action(self, action_type):
        return self.filter(action_type=action_type)

    def latest(self, *fields):
        if fields:
            return super().latest(*fields)
        return self.order_by('-created_at', '-id')


class ActivityLog(models.Model):
    """Historical audit record for the MADAM HY business domain.

    Activity logs are immutable audit records that capture system events, user actions,
    and entity mutations for security compliance and operational transparency.
    """

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

    objects = ActivityLogQuerySet.as_manager()

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

        # Enforce immutability on existing records
        if self.pk:
            try:
                orig = ActivityLog.objects.get(pk=self.pk)
                immutable_fields = [
                    'actor_id', 'action_type', 'action_label', 'description',
                    'content_type_id', 'object_id',
                ]
                for field in immutable_fields:
                    if getattr(orig, field) != getattr(self, field):
                        raise ValidationError(
                            f'Activity log records are immutable. Field {field} cannot be modified.'
                        )
            except ActivityLog.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.metadata is None:
            self.metadata = {}
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Disallow deletion of historical audit log records to preserve audit compliance."""
        raise ValidationError('Historical activity log records must be preserved. They cannot be deleted.')

    @property
    def content_object(self):
        return self.related_object

    @property
    def ip_address(self):
        """Extract IP address from metadata if recorded."""
        if isinstance(self.metadata, dict):
            return self.metadata.get('ip_address') or self.metadata.get('ip') or ''
        return ''

    @property
    def user_agent(self):
        """Extract User-Agent string from metadata if recorded."""
        if isinstance(self.metadata, dict):
            return self.metadata.get('user_agent', '')
        return ''

    @property
    def changes_diff(self):
        """Extract structured before/after state diff from metadata if present."""
        if not isinstance(self.metadata, dict):
            return {}

        if 'diff' in self.metadata and isinstance(self.metadata['diff'], dict):
            return self.metadata['diff']
        if 'changes' in self.metadata and isinstance(self.metadata['changes'], dict):
            return self.metadata['changes']

        old_values = self.metadata.get('old_values') or self.metadata.get('before')
        new_values = self.metadata.get('new_values') or self.metadata.get('after')
        if isinstance(old_values, dict) and isinstance(new_values, dict):
            all_keys = set(old_values.keys()) | set(new_values.keys())
            diff = {}
            for k in all_keys:
                diff[k] = {'old': old_values.get(k), 'new': new_values.get(k)}
            return diff
        return {}
