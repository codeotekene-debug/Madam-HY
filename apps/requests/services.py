import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.products.models import Product

from .models import Request

User = get_user_model()
STAFF_MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
STATUS_ALIASES = {
    'IN_REVIEW': Request.Status.REVIEWING,
    'IN REVIEW': Request.Status.REVIEWING,
    'IN_PROGRESS': Request.Status.REVIEWING,
    'IN PROGRESS': Request.Status.REVIEWING,
    'RESOLVED': Request.Status.COMPLETED,
    'CLOSED': Request.Status.COMPLETED,
}


class RequestService:
    """Service layer coordinating request creation, lifecycle transitions, assignment, and notifications."""

    @classmethod
    def normalize_status(cls, status_str):
        if not status_str:
            return None
        cleaned = str(status_str).strip().upper()
        if cleaned in STATUS_ALIASES:
            return STATUS_ALIASES[cleaned]
        for val, _ in Request.Status.choices:
            if cleaned == val:
                return val
        return cleaned

    @classmethod
    def normalize_priority(cls, priority_str):
        if not priority_str:
            return Request.Priority.NORMAL
        cleaned = str(priority_str).strip().upper()
        for val, _ in Request.Priority.choices:
            if cleaned == val:
                return val
        return cleaned

    @classmethod
    def normalize_request_type(cls, type_str):
        if not type_str:
            return Request.RequestType.GENERAL
        cleaned = str(type_str).strip().upper()
        # Support display names like 'PRODUCT REQUEST' -> 'PRODUCT'
        if 'PRODUCT' in cleaned:
            return Request.RequestType.PRODUCT
        if 'SUPPORT' in cleaned:
            return Request.RequestType.SUPPORT
        if 'OTHER' in cleaned:
            return Request.RequestType.OTHER
        if 'GENERAL' in cleaned:
            return Request.RequestType.GENERAL
        for val, _ in Request.RequestType.choices:
            if cleaned == val:
                return val
        return cleaned

    @classmethod
    @transaction.atomic
    def create_request(
        cls,
        customer,
        title,
        description,
        request_type=Request.RequestType.GENERAL,
        priority=Request.Priority.NORMAL,
        product=None,
        quantity=None,
        notes='',
        attachment=None,
        actor=None,
    ):
        """Create a new customer request with strict validation and audit logging."""
        if not customer:
            raise ValidationError({'customer': 'Customer is required.'})

        if getattr(customer, 'role', None) != 'CUSTOMER':
            raise ValidationError({'customer': 'Only CUSTOMER role users can create requests.'})

        clean_title = (title or '').strip()
        if not clean_title:
            raise ValidationError({'title': 'Title is required.'})

        clean_description = (description or '').strip()
        if not clean_description:
            raise ValidationError({'description': 'Description is required.'})

        req_type = cls.normalize_request_type(request_type)
        if req_type not in Request.RequestType.values:
            raise ValidationError({'request_type': f'Invalid request type: {request_type}'})

        clean_priority = cls.normalize_priority(priority)
        if clean_priority not in Request.Priority.values:
            raise ValidationError({'priority': f'Invalid priority: {priority}'})

        product_obj = None
        if product:
            if isinstance(product, Product):
                product_obj = product
            else:
                try:
                    product_obj = Product.objects.get(pk=product)
                except (Product.DoesNotExist, ValueError):
                    raise ValidationError({'product': 'Selected product does not exist.'})

        if req_type == Request.RequestType.PRODUCT and not product_obj:
            raise ValidationError({'product': 'Product requests should normally include a product.'})

        qty = None
        if quantity is not None and str(quantity).strip() != '':
            try:
                qty = int(quantity)
                if qty <= 0:
                    raise ValidationError({'quantity': 'Quantity must be positive when supplied.'})
            except (ValueError, TypeError):
                raise ValidationError({'quantity': 'Quantity must be a positive integer.'})

        request_number = f'REQ-{uuid.uuid4().hex[:8].upper()}'

        request_obj = Request(
            request_number=request_number,
            customer=customer,
            request_type=req_type,
            title=clean_title,
            description=clean_description,
            status=Request.Status.PENDING,
            priority=clean_priority,
            product=product_obj,
            quantity=qty,
            notes=(notes or '').strip(),
        )

        if attachment:
            request_obj.attachment = attachment

        request_obj.full_clean()
        request_obj.save()

        # Audit log
        log_actor = actor or customer
        try:
            log_activity(
                actor=log_actor,
                action_type=ActivityLog.ActionType.CREATED,
                action_label='Request Created',
                description=f'Request {request_obj.request_number} was created: {request_obj.title}',
                related_object=request_obj,
                metadata={
                    'request_id': request_obj.id,
                    'request_number': request_obj.request_number,
                    'customer_id': customer.id,
                    'request_type': request_obj.request_type,
                    'priority': request_obj.priority,
                },
            )
        except Exception:
            pass

        # In-app notifications to staff
        try:
            staff_users = User.objects.filter(role__in=STAFF_MANAGEMENT_ROLES, is_active=True)
            for staff in staff_users:
                create_notification(
                    recipient=staff,
                    notification_type=Notification.NotificationType.REQUEST,
                    title='New Customer Request',
                    message=f'New {request_obj.get_priority_display()} request {request_obj.request_number} from {customer.get_full_name() or customer.username}: {request_obj.title}',
                    priority=Notification.Priority.URGENT if request_obj.priority == Request.Priority.URGENT else Notification.Priority.NORMAL,
                    related_object=request_obj,
                    action_url=f'/requests/{request_obj.uuid}/',
                )
        except Exception:
            pass

        return request_obj

    @classmethod
    @transaction.atomic
    def update_status(cls, request_obj, new_status, actor, resolution='', notes=''):
        """Transition request lifecycle with permission validation, audit logging, and customer notification."""
        if not actor or not getattr(actor, 'is_authenticated', False):
            raise PermissionDenied('Authentication is required to update request status.')

        if getattr(actor, 'role', None) not in STAFF_MANAGEMENT_ROLES:
            raise PermissionDenied('Only staff or management can update request status.')

        old_status = request_obj.status
        normalized = cls.normalize_status(new_status)
        if normalized not in Request.Status.values:
            raise ValidationError({'status': f'Invalid status: {new_status}'})

        # Terminal state guards: Cannot transition from completed/rejected/cancelled unless manager/owner
        terminal_states = {Request.Status.COMPLETED, Request.Status.REJECTED, Request.Status.CANCELLED}
        if old_status in terminal_states and normalized != old_status:
            if getattr(actor, 'role', None) not in ('OWNER', 'MANAGER'):
                raise ValidationError({'status': f'Cannot transition request from closed status {old_status}.'})

        # Validation rules for completion
        clean_resolution = (resolution or '').strip()
        if normalized == Request.Status.COMPLETED:
            effective_resolution = clean_resolution or request_obj.resolution.strip() or (notes or '').strip()
            if not effective_resolution:
                raise ValidationError({'resolution': 'Completed requests must include a resolution or response.'})
            request_obj.resolution = effective_resolution

        if clean_resolution:
            request_obj.resolution = clean_resolution

        clean_notes = (notes or '').strip()
        if clean_notes:
            if request_obj.notes:
                request_obj.notes = f'{request_obj.notes}\n[{timezone.now().strftime("%Y-%m-%d %H:%M")}] {clean_notes}'
            else:
                request_obj.notes = clean_notes

        request_obj.status = normalized

        if normalized in terminal_states and not request_obj.resolved_at:
            request_obj.resolved_at = timezone.now()

        request_obj.full_clean()
        request_obj.save()

        # Audit log
        action_type = ActivityLog.ActionType.UPDATED
        if normalized == Request.Status.APPROVED:
            action_type = ActivityLog.ActionType.APPROVED
        elif normalized in (Request.Status.REJECTED, Request.Status.CANCELLED):
            action_type = ActivityLog.ActionType.REJECTED

        try:
            log_activity(
                actor=actor,
                action_type=action_type,
                action_label='Request Status Updated',
                description=f'Request {request_obj.request_number} status updated from {old_status} to {normalized}.',
                related_object=request_obj,
                metadata={
                    'previous_status': old_status,
                    'new_status': normalized,
                    'resolution': request_obj.resolution,
                    'updated_by': actor.username,
                },
            )
        except Exception:
            pass

        # Notify customer
        if request_obj.customer and request_obj.customer != actor:
            try:
                msg = f'Your request {request_obj.request_number} ("{request_obj.title}") status has been updated to {request_obj.get_status_display()}.'
                if request_obj.resolution:
                    msg += f' Resolution: {request_obj.resolution}'
                create_notification(
                    recipient=request_obj.customer,
                    notification_type=Notification.NotificationType.REQUEST,
                    title=f'Request Status Update: {request_obj.request_number}',
                    message=msg,
                    related_object=request_obj,
                    action_url=f'/requests/{request_obj.uuid}/',
                )
            except Exception:
                pass

        return request_obj

    @classmethod
    @transaction.atomic
    def assign_request(cls, request_obj, staff_user, actor):
        """Assign or reassign request to a staff member with permission check, audit log, and notification."""
        if not actor or not getattr(actor, 'is_authenticated', False):
            raise PermissionDenied('Authentication is required to assign requests.')

        if getattr(actor, 'role', None) not in STAFF_MANAGEMENT_ROLES:
            raise PermissionDenied('Only staff or management can assign requests.')

        target_staff = None
        if staff_user:
            if isinstance(staff_user, User):
                target_staff = staff_user
            else:
                try:
                    # Support ID or username
                    if str(staff_user).isdigit():
                        target_staff = User.objects.get(pk=int(staff_user))
                    else:
                        target_staff = User.objects.get(username=str(staff_user).strip())
                except User.DoesNotExist:
                    raise ValidationError({'assigned_to': 'Selected staff member does not exist.'})

            if target_staff.role not in STAFF_MANAGEMENT_ROLES or target_staff.role == 'CUSTOMER':
                raise ValidationError({'assigned_to': 'Assigned user must have an authorized staff role.'})

        old_assignee = request_obj.assigned_to
        request_obj.assigned_to = target_staff

        # If pending and assigned, advance status to REVIEWING
        if target_staff and request_obj.status == Request.Status.PENDING:
            request_obj.status = Request.Status.REVIEWING

        request_obj.full_clean()
        request_obj.save()

        # Audit log
        assignee_name = target_staff.get_full_name() or target_staff.username if target_staff else 'Unassigned'
        try:
            log_activity(
                actor=actor,
                action_type=ActivityLog.ActionType.UPDATED,
                action_label='Request Assigned',
                description=f'Request {request_obj.request_number} assigned to {assignee_name}.',
                related_object=request_obj,
                metadata={
                    'previous_assignee': old_assignee.username if old_assignee else None,
                    'new_assignee': target_staff.username if target_staff else None,
                    'assigned_by': actor.username,
                },
            )
        except Exception:
            pass

        # Notify assignee
        if target_staff and target_staff != actor:
            try:
                create_notification(
                    recipient=target_staff,
                    notification_type=Notification.NotificationType.REQUEST,
                    title='Request Assigned to You',
                    message=f'You have been assigned to handle request {request_obj.request_number}: {request_obj.title}',
                    related_object=request_obj,
                    action_url=f'/requests/{request_obj.uuid}/',
                )
            except Exception:
                pass

        return request_obj

    @classmethod
    def get_summary_metrics(cls, queryset=None):
        """Calculate counts for summary cards and reporting."""
        qs = queryset if queryset is not None else Request.objects.all()
        counts = qs.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=Request.Status.PENDING)),
            reviewing=Count('id', filter=Q(status__in=[Request.Status.REVIEWING, Request.Status.PROCESSING])),
            approved=Count('id', filter=Q(status=Request.Status.APPROVED)),
            completed=Count('id', filter=Q(status=Request.Status.COMPLETED)),
            rejected=Count('id', filter=Q(status=Request.Status.REJECTED)),
            cancelled=Count('id', filter=Q(status=Request.Status.CANCELLED)),
            urgent=Count('id', filter=Q(priority=Request.Priority.URGENT)),
        )

        return {
            'total': counts['total'] or 0,
            'pending': counts['pending'] or 0,
            'in_review': counts['reviewing'] or 0,
            'approved': counts['approved'] or 0,
            'completed': counts['completed'] or 0,
            'rejected': counts['rejected'] or 0,
            'cancelled': counts['cancelled'] or 0,
            'urgent': counts['urgent'] or 0,
        }
