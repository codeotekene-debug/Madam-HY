from datetime import datetime, timedelta
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone

from apps.activity_logs.models import ActivityLog


class ActivityLogService:
    """Central service layer for audit logging, query filtering, metrics, and serialization."""

    ACTION_TYPE_ALIASES = {
        'CREATE': ActivityLog.ActionType.CREATED,
        'CREATED': ActivityLog.ActionType.CREATED,
        'UPDATE': ActivityLog.ActionType.UPDATED,
        'UPDATED': ActivityLog.ActionType.UPDATED,
        'DELETE': ActivityLog.ActionType.DELETED,
        'DELETED': ActivityLog.ActionType.DELETED,
        'VIEW': ActivityLog.ActionType.VIEWED,
        'VIEWED': ActivityLog.ActionType.VIEWED,
        'APPROVE': ActivityLog.ActionType.APPROVED,
        'APPROVAL': ActivityLog.ActionType.APPROVED,
        'APPROVED': ActivityLog.ActionType.APPROVED,
        'REJECT': ActivityLog.ActionType.REJECTED,
        'REJECTION': ActivityLog.ActionType.REJECTED,
        'REJECTED': ActivityLog.ActionType.REJECTED,
        'PAYMENT': ActivityLog.ActionType.PAYMENT,
        'PAY': ActivityLog.ActionType.PAYMENT,
        'INVENTORY': ActivityLog.ActionType.INVENTORY,
        'STOCK': ActivityLog.ActionType.INVENTORY,
        'SYSTEM': ActivityLog.ActionType.SYSTEM,
        'LOGIN': ActivityLog.ActionType.SYSTEM,
        'LOGOUT': ActivityLog.ActionType.SYSTEM,
    }

    @classmethod
    def normalize_action_type(cls, action):
        """Map action aliases to canonical ActionType choices."""
        if not action:
            return None
        upper_val = str(action).strip().upper()
        return cls.ACTION_TYPE_ALIASES.get(upper_val, upper_val if upper_val in ActivityLog.ActionType.values else None)

    @classmethod
    def log_activity(
        cls,
        actor,
        action_type,
        action_label,
        description,
        related_object=None,
        metadata=None,
        request=None,
        ip_address=None,
        user_agent=None,
    ):
        """Create a historical audit log entry with optional client telemetry."""
        if not action_type:
            raise ValueError('Action type is required.')
        if not action_label or not str(action_label).strip():
            raise ValueError('Action label is required.')
        if not description or not str(description).strip():
            raise ValueError('Description is required.')

        normalized_action = cls.normalize_action_type(action_type) or str(action_type).upper()

        meta = dict(metadata) if metadata and isinstance(metadata, dict) else (metadata or {})

        # Extract client telemetry from request if supplied
        if request is not None:
            if not ip_address:
                xff = request.META.get('HTTP_X_FORWARDED_FOR')
                if xff:
                    ip_address = xff.split(',')[0].strip()
                else:
                    ip_address = request.META.get('REMOTE_ADDR') or ''
            if not user_agent:
                user_agent = request.META.get('HTTP_USER_AGENT') or ''

        if ip_address and 'ip_address' not in meta:
            meta['ip_address'] = ip_address
        if user_agent and 'user_agent' not in meta:
            meta['user_agent'] = user_agent

        log = ActivityLog(
            actor=actor,
            action_type=normalized_action,
            action_label=str(action_label).strip(),
            description=str(description).strip(),
            metadata=meta,
        )

        if related_object is not None:
            log.related_object = related_object

        log.save()
        return log

    @classmethod
    def get_activity_logs(
        cls,
        action=None,
        actor_id=None,
        entity=None,
        start_date=None,
        end_date=None,
        search=None,
    ):
        """Retrieve audit logs with comprehensive multi-criteria filtering."""
        qs = ActivityLog.objects.select_related('actor', 'content_type').all().order_by('-created_at', '-id')

        # Filter by action type
        if action:
            normalized_action = cls.normalize_action_type(action)
            if normalized_action:
                qs = qs.filter(action_type=normalized_action)

        # Filter by actor
        if actor_id:
            actor_str = str(actor_id).strip()
            if actor_str.isdigit():
                qs = qs.filter(actor__id=int(actor_str))
            else:
                qs = qs.filter(actor__username__iexact=actor_str)

        # Filter by entity / content type model
        if entity:
            entity_str = str(entity).strip().lower()
            qs = qs.filter(content_type__model__iexact=entity_str)

        # Filter by date range
        if start_date:
            parsed_start = cls._parse_date(start_date)
            if parsed_start:
                qs = qs.filter(created_at__date__gte=parsed_start)

        if end_date:
            parsed_end = cls._parse_date(end_date)
            if parsed_end:
                qs = qs.filter(created_at__date__lte=parsed_end)

        # Keyword search
        if search:
            search_term = str(search).strip()
            if search_term:
                qs = qs.filter(
                    Q(description__icontains=search_term)
                    | Q(action_label__icontains=search_term)
                    | Q(actor__username__icontains=search_term)
                    | Q(actor__email__icontains=search_term)
                    | Q(actor__first_name__icontains=search_term)
                    | Q(actor__last_name__icontains=search_term)
                    | Q(metadata__icontains=search_term)
                )

        return qs

    @staticmethod
    def _parse_date(val):
        """Safely parse date strings into date objects."""
        if isinstance(val, (datetime, timezone.datetime)):
            return val.date()
        if hasattr(val, 'strftime'):
            return val
        if isinstance(val, str):
            try:
                return datetime.strptime(val.strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None
        return None

    @classmethod
    def get_activity_metrics(cls):
        """Compute summary statistics for management audit overview."""
        now = timezone.now()
        today = now.date()
        yesterday = today - timedelta(days=1)
        last_24h = now - timedelta(hours=24)

        total_logs = ActivityLog.objects.count()
        today_logs = ActivityLog.objects.filter(created_at__date=today).count()
        last_24h_logs = ActivityLog.objects.filter(created_at__gte=last_24h).count()

        # Action breakdown
        actions_counts = (
            ActivityLog.objects.values('action_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        actions_breakdown = {row['action_type']: row['count'] for row in actions_counts}

        # Top actors
        top_actors_qs = (
            ActivityLog.objects.filter(actor__isnull=False)
            .values('actor__id', 'actor__username', 'actor__role', 'actor__first_name', 'actor__last_name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )
        top_actors = [
            {
                'id': a['actor__id'],
                'username': a['actor__username'],
                'name': f"{a['actor__first_name']} {a['actor__last_name']}".strip() or a['actor__username'],
                'role': a['actor__role'],
                'count': a['count'],
            }
            for a in top_actors_qs
        ]

        # Available entities
        available_entities = list(
            ActivityLog.objects.filter(content_type__isnull=False)
            .values_list('content_type__model', flat=True)
            .distinct()
            .order_by('content_type__model')
        )

        return {
            'total_logs': total_logs,
            'today_logs': today_logs,
            'last_24h_logs': last_24h_logs,
            'actions_breakdown': actions_breakdown,
            'top_actors': top_actors,
            'available_entities': available_entities,
        }

    @classmethod
    def serialize_activity_log(cls, log):
        """Serialize an activity log entry into a dictionary for JSON API responses."""
        if log is None:
            return None

        actor_dict = None
        if log.actor:
            actor_dict = {
                'id': log.actor.id,
                'username': log.actor.username,
                'email': log.actor.email,
                'name': log.actor.get_full_name() or log.actor.username,
                'role': log.actor.role,
            }

        return {
            'id': log.id,
            'actor': actor_dict,
            'action_type': log.action_type,
            'action_type_display': log.get_action_type_display(),
            'action_label': log.action_label,
            'description': log.description,
            'entity': log.content_type.model.title() if log.content_type else None,
            'entity_model': log.content_type.model if log.content_type else None,
            'object_id': log.object_id,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
            'metadata': log.metadata or {},
            'changes_diff': log.changes_diff,
            'created_at': log.created_at.isoformat() if log.created_at else None,
            'created_at_display': log.created_at.strftime('%b %d, %Y %H:%M:%S') if log.created_at else '',
        }


# =============================================================================
# Standalone functions for backward compatibility with existing codebase
# =============================================================================


def log_activity(
    actor,
    action_type,
    action_label,
    description,
    related_object=None,
    metadata=None,
    request=None,
    ip_address=None,
    user_agent=None,
):
    """Standalone wrapper maintaining backward compatibility for log_activity."""
    return ActivityLogService.log_activity(
        actor=actor,
        action_type=action_type,
        action_label=action_label,
        description=description,
        related_object=related_object,
        metadata=metadata,
        request=request,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_model_activity(
    actor,
    action_type,
    action_label,
    description,
    model_instance=None,
    metadata=None,
    request=None,
    ip_address=None,
    user_agent=None,
):
    """Standalone wrapper maintaining backward compatibility for log_model_activity."""
    return ActivityLogService.log_activity(
        actor=actor,
        action_type=action_type,
        action_label=action_label,
        description=description,
        related_object=model_instance,
        metadata=metadata,
        request=request,
        ip_address=ip_address,
        user_agent=user_agent,
    )
