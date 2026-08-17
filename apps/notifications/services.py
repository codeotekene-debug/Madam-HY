from django.utils import timezone

from apps.notifications.models import Notification


def create_notification(
    recipient,
    notification_type,
    title,
    message,
    priority=Notification.Priority.NORMAL,
    related_object=None,
    action_url='',
):
    if recipient is None:
        raise ValueError('Notification recipient is required.')
    if not title or not message:
        raise ValueError('Notification title and message are required.')

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
    return notification


def mark_all_notifications_as_read(user):
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )


def unread_notifications_count(user):
    return Notification.objects.filter(recipient=user, is_read=False).count()
