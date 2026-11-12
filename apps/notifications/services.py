from datetime import datetime
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification

try:
    from apps.activity_logs.services import log_activity
except ImportError:
    log_activity = None


class NotificationService:
    """Central service layer for notification creation, querying, and lifecycle management."""

    @staticmethod
    def create_notification(
        recipient,
        notification_type,
        title,
        message,
        priority=Notification.Priority.NORMAL,
        related_object=None,
        action_url='',
        actor=None,
    ):
        """Create a new in-app notification with strict input validation."""
        if recipient is None:
            raise ValueError('Notification recipient is required.')
        if not title or not str(title).strip():
            raise ValueError('Notification title and message are required.')
        if not message or not str(message).strip():
            raise ValueError('Notification title and message are required.')

        title = str(title).strip()
        message = str(message).strip()

        # Validate notification_type against choices
        valid_types = [c[0] for c in Notification.NotificationType.choices]
        if str(notification_type).upper() in valid_types:
            notification_type = str(notification_type).upper()

        # Validate priority against choices
        valid_priorities = [c[0] for c in Notification.Priority.choices]
        if str(priority).upper() in valid_priorities:
            priority = str(priority).upper()

        notification = Notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            priority=priority,
            action_url=action_url or '',
        )
        if related_object is not None:
            notification.related_object = related_object

        notification.save()

        if log_activity and actor is not None:
            try:
                log_activity(
                    actor=actor,
                    action_type='CREATED',
                    action_label='Notification created',
                    description=f'Notification "{title}" created for {recipient.username}.',
                    target=notification,
                )
            except Exception:
                pass

        return notification

    @staticmethod
    def get_user_notifications(user, is_read=None, notification_type=None, priority=None, search=None):
        """Retrieve notifications for a specific user with filtering and newest-first ordering."""
        if not user or not getattr(user, 'is_authenticated', False):
            return Notification.objects.none()

        qs = Notification.objects.filter(recipient=user)

        if is_read is not None:
            qs = qs.filter(is_read=bool(is_read))

        if notification_type:
            type_val = str(notification_type).strip().upper()
            if type_val in Notification.NotificationType.values:
                qs = qs.filter(notification_type=type_val)

        if priority:
            prio_val = str(priority).strip().upper()
            if prio_val in Notification.Priority.values:
                qs = qs.filter(priority=prio_val)

        if search:
            search_term = str(search).strip()
            if search_term:
                qs = qs.filter(Q(title__icontains=search_term) | Q(message__icontains=search_term))

        return qs.order_by('-created_at', '-id')

    @staticmethod
    def get_unread_count(user):
        """Return the total number of unread notifications for a user."""
        if not user or not getattr(user, 'is_authenticated', False):
            return 0
        return Notification.objects.filter(recipient=user, is_read=False).count()

    @staticmethod
    def get_notification_metrics(user):
        """Compute summary notification counts for user inbox overview."""
        if not user or not getattr(user, 'is_authenticated', False):
            return {'total': 0, 'unread': 0, 'read': 0, 'urgent_unread': 0}

        user_notifications = Notification.objects.filter(recipient=user)
        total = user_notifications.count()
        unread = user_notifications.filter(is_read=False).count()
        read = total - unread
        urgent_unread = user_notifications.filter(
            is_read=False, priority=Notification.Priority.URGENT
        ).count()

        return {
            'total': total,
            'unread': unread,
            'read': read,
            'urgent_unread': urgent_unread,
        }

    @classmethod
    def mark_as_read(cls, notification_or_id, user=None):
        """Mark a notification as read, enforcing user ownership and recording timestamp."""
        if isinstance(notification_or_id, Notification):
            notification = notification_or_id
        else:
            try:
                notif_id = int(notification_or_id)
            except (ValueError, TypeError):
                raise ValueError(f'Invalid notification ID: {notification_or_id}')

            notification = Notification.objects.filter(pk=notif_id).first()
            if not notification:
                raise Notification.DoesNotExist(f'Notification with ID {notif_id} does not exist.')

        if user is not None and notification.recipient != user:
            raise PermissionDenied('Permission denied. You cannot modify notifications belonging to another user.')

        notification.mark_as_read()
        return notification

    @classmethod
    def mark_as_unread(cls, notification_or_id, user=None):
        """Mark a notification as unread, enforcing user ownership."""
        if isinstance(notification_or_id, Notification):
            notification = notification_or_id
        else:
            try:
                notif_id = int(notification_or_id)
            except (ValueError, TypeError):
                raise ValueError(f'Invalid notification ID: {notification_or_id}')

            notification = Notification.objects.filter(pk=notif_id).first()
            if not notification:
                raise Notification.DoesNotExist(f'Notification with ID {notif_id} does not exist.')

        if user is not None and notification.recipient != user:
            raise PermissionDenied('Permission denied. You cannot modify notifications belonging to another user.')

        notification.mark_as_unread()
        return notification

    @staticmethod
    def mark_all_as_read(user):
        """Bulk-mark all unread notifications for a user as read."""
        if not user or not getattr(user, 'is_authenticated', False):
            return 0
        return Notification.objects.filter(recipient=user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )

    @staticmethod
    def serialize_notification(notification):
        """Serialize a notification record into a clean dictionary."""
        if notification is None:
            return None

        # Relative time / display string
        created_at_iso = notification.created_at.isoformat() if notification.created_at else None
        read_at_iso = notification.read_at.isoformat() if notification.read_at else None

        created_at_display = ''
        if notification.created_at:
            created_at_display = notification.created_at.strftime('%b %d, %Y %H:%M')

        return {
            'id': notification.id,
            'recipient_id': notification.recipient_id,
            'notification_type': notification.notification_type,
            'notification_type_display': notification.get_notification_type_display(),
            'title': notification.title,
            'message': notification.message,
            'priority': notification.priority,
            'priority_display': notification.get_priority_display(),
            'is_read': notification.is_read,
            'read_at': read_at_iso,
            'action_url': notification.action_url or '',
            'created_at': created_at_iso,
            'created_at_display': created_at_display,
            'related_object_id': str(notification.object_id) if notification.object_id else None,
        }


# =============================================================================
# Standalone functions for backward compatibility with existing codebase
# =============================================================================


def create_notification(
    recipient,
    notification_type,
    title,
    message,
    priority=Notification.Priority.NORMAL,
    related_object=None,
    action_url='',
):
    """Standalone wrapper maintaining backward compatibility for create_notification."""
    return NotificationService.create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        related_object=related_object,
        action_url=action_url,
    )


def mark_all_notifications_as_read(user):
    """Standalone wrapper maintaining backward compatibility for mark_all_notifications_as_read."""
    return NotificationService.mark_all_as_read(user)


def unread_notifications_count(user):
    """Standalone wrapper maintaining backward compatibility for unread_notifications_count."""
    return NotificationService.get_unread_count(user)
