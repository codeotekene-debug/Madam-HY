from django.contrib.contenttypes.models import ContentType

from apps.activity_logs.models import ActivityLog


def log_activity(
    actor,
    action_type,
    action_label,
    description,
    related_object=None,
    metadata=None,
):
    """Create a historical audit log entry without becoming a transactional source of truth."""

    if not action_type:
        raise ValueError('Action type is required.')
    if not action_label or not action_label.strip():
        raise ValueError('Action label is required.')
    if not description or not description.strip():
        raise ValueError('Description is required.')

    log = ActivityLog(
        actor=actor,
        action_type=action_type,
        action_label=action_label.strip(),
        description=description.strip(),
        metadata=metadata or {},
    )

    if related_object is not None:
        log.related_object = related_object
    log.save()
    return log


def log_model_activity(actor, action_type, action_label, description, model_instance=None, metadata=None):
    if model_instance is not None:
        content_type = ContentType.objects.get_for_model(model_instance)
        return log_activity(
            actor=actor,
            action_type=action_type,
            action_label=action_label,
            description=description,
            related_object=model_instance,
            metadata=metadata,
        )
    return log_activity(
        actor=actor,
        action_type=action_type,
        action_label=action_label,
        description=description,
        metadata=metadata,
    )
