import hashlib
import secrets
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.delivery.models import (
    Delivery,
    DeliverySetting,
    DeliveryStatusHistory,
    DeliveryZone,
    RiderProfile,
    DeliveryAssignment,
)
from apps.notifications.services import NotificationService
from apps.notifications.models import Notification

User = get_user_model()


class DeliveryService:
    """Core domain service orchestrating the delivery lifecycle and rider management."""

    @staticmethod
    def _generate_tracking_number(order):
        """Generate formatted tracking reference (e.g. MH-DEL-10501)."""
        suffix = secrets.token_hex(2).upper()
        clean_order_num = (order.order_number or '').replace('MH-ORD-', '').replace('ORD-', '')
        return f"MH-DEL-{clean_order_num or order.id}-{suffix}"

    @classmethod
    @transaction.atomic
    def create_delivery_for_order(cls, order, zone=None, instructions='', created_by=None):
        """
        Create a new Delivery record for an Order.
        Prevents duplicate deliveries for the same order.
        """
        if hasattr(order, 'delivery') and order.delivery:
            return order.delivery

        # Determine zone
        if zone is None and order.delivery_zone:
            zone = order.delivery_zone

        # Order fee is a checkout snapshot. Do not silently substitute a current zone fee.
        delivery_fee = order.delivery_fee if order.delivery_fee is not None else Decimal('0.00')
        tracking_number = cls._generate_tracking_number(order)

        customer_name = ''
        customer_phone = order.customer_phone or ''
        if order.customer:
            customer_name = order.customer.get_full_name() or order.customer.username
            if not customer_phone:
                customer_phone = getattr(order.customer, 'phone_number', '') or ''

        delivery = Delivery.objects.create(
            order=order,
            tracking_number=tracking_number,
            zone=zone,
            delivery_fee=delivery_fee,
            status=Delivery.DeliveryStatus.PENDING_ASSIGNMENT,
            customer_name=customer_name,
            customer_phone=customer_phone,
            delivery_address=order.delivery_address or 'Store Pickup / Address not provided',
            delivery_instructions=instructions or order.notes or '',
        )

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status='NONE',
            to_status=Delivery.DeliveryStatus.PENDING_ASSIGNMENT,
            changed_by=created_by,
            comment=f"Delivery created for order {order.order_number}",
        )

        return delivery

    @classmethod
    @transaction.atomic
    def assign_rider(cls, delivery, rider_user, assigned_by=None):
        """Assign or reassign a rider to a delivery with validation."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.order.status not in ['CONFIRMED', 'PROCESSING', 'READY']:
            raise ValidationError('The order must be confirmed and prepared before rider assignment.')
        if delivery.order.payment_status not in ['CONFIRMED', 'PAID_BY_CREDIT'] and delivery.order.payment_method != 'CASH':
            raise ValidationError('Payment must be confirmed before assigning a rider.')

        if delivery.status in [Delivery.DeliveryStatus.DELIVERED, Delivery.DeliveryStatus.CANCELLED]:
            raise ValidationError(f"Cannot assign rider to a {delivery.get_status_display()} delivery.")

        if rider_user.role != 'RIDER':
            raise ValidationError(f"Selected user '{rider_user.username}' is not a delivery rider.")

        if not rider_user.is_active:
            raise ValidationError(f"Rider account '{rider_user.username}' is inactive.")

        rider_profile = getattr(rider_user, 'rider_profile', None)
        if rider_profile and not rider_profile.can_accept_more:
            raise ValidationError(
                f"Rider '{rider_user.get_full_name() or rider_user.username}' has reached max concurrent deliveries or is unavailable."
            )

        previous_status = delivery.status
        previous_rider = delivery.rider

        if previous_rider_id := getattr(previous_rider, 'id', None):
            DeliveryAssignment.objects.filter(
                delivery=delivery, rider_id=previous_rider_id,
                status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED],
            ).update(status=DeliveryAssignment.AssignmentStatus.REASSIGNED, ended_at=timezone.now())

        delivery.rider = rider_user
        delivery.status = Delivery.DeliveryStatus.ASSIGNED
        delivery.assigned_at = timezone.now()
        delivery.rejection_reason = ''
        delivery.save()

        DeliveryAssignment.objects.create(
            delivery=delivery, rider=rider_user, assigned_by=assigned_by,
            status=DeliveryAssignment.AssignmentStatus.ASSIGNED if not previous_rider else DeliveryAssignment.AssignmentStatus.REASSIGNED,
            reason='Reassigned' if previous_rider else '',
        )

        action_label = "Rider Reassigned" if previous_rider else "Rider Assigned"
        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=previous_status,
            to_status=Delivery.DeliveryStatus.ASSIGNED,
            changed_by=assigned_by,
            comment=f"{action_label}: Assigned to {rider_user.get_full_name() or rider_user.username}",
        )

        # Notify rider
        try:
            NotificationService.create_notification(
                recipient=rider_user,
                notification_type=Notification.NotificationType.ORDER,
                title="New Delivery Assignment",
                message=f"You have been assigned Order {delivery.order.order_number} for delivery to {delivery.delivery_address}.",
                priority=Notification.Priority.HIGH,
                related_object=delivery,
                action_url=f"/rider/assignments/",
                actor=assigned_by,
            )
        except Exception:
            pass

        # Notify customer
        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Rider Assigned to Your Order",
                    message=f"Rider {rider_user.get_full_name() or 'A driver'} has been assigned to deliver Order {delivery.order.order_number}.",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=assigned_by,
                )
            except Exception:
                pass

        # If previous rider existed, notify them of reassignment
        if previous_rider and previous_rider != rider_user:
            try:
                NotificationService.create_notification(
                    recipient=previous_rider,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Job Reassigned",
                    message=f"Order {delivery.order.order_number} has been reassigned to another rider.",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url="/rider/deliveries/",
                    actor=assigned_by,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def rider_accept_delivery(cls, delivery, rider_user):
        """Rider accepts an assigned delivery."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.rider != rider_user:
            raise PermissionDenied("You can only accept deliveries assigned to you.")

        if delivery.status != Delivery.DeliveryStatus.ASSIGNED:
            raise ValidationError(f"Cannot accept delivery currently in '{delivery.get_status_display()}' state.")

        delivery.status = Delivery.DeliveryStatus.ACCEPTED
        delivery.accepted_at = timezone.now()
        delivery.save(update_fields=['status', 'accepted_at', 'updated_at'])

        DeliveryAssignment.objects.filter(delivery=delivery, rider=rider_user, status=DeliveryAssignment.AssignmentStatus.ASSIGNED).update(status=DeliveryAssignment.AssignmentStatus.ACCEPTED, accepted_at=timezone.now())

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=Delivery.DeliveryStatus.ASSIGNED,
            to_status=Delivery.DeliveryStatus.ACCEPTED,
            changed_by=rider_user,
            comment=f"Accepted by rider {rider_user.get_full_name() or rider_user.username}",
        )

        # Notify customer
        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Accepted by Rider",
                    message=f"Rider {rider_user.get_full_name() or 'A driver'} has accepted your delivery order #{delivery.order.order_number} and is preparing for pickup.",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def rider_reject_delivery(cls, delivery, rider_user, reason):
        """Rider rejects an assigned delivery with a required reason."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.rider != rider_user:
            raise PermissionDenied("You can only reject deliveries assigned to you.")

        if delivery.status != Delivery.DeliveryStatus.ASSIGNED:
            raise ValidationError(f"Cannot reject delivery currently in '{delivery.get_status_display()}' state.")

        if not reason or not str(reason).strip():
            raise ValidationError({'reason': 'A rejection reason is required.'})

        reason_str = str(reason).strip()
        previous_rider = delivery.rider
        DeliveryAssignment.objects.filter(delivery=delivery, rider=previous_rider, status=DeliveryAssignment.AssignmentStatus.ASSIGNED).update(status=DeliveryAssignment.AssignmentStatus.REJECTED, reason=reason_str, ended_at=timezone.now())
        delivery.rider = None
        delivery.status = Delivery.DeliveryStatus.PENDING_ASSIGNMENT
        delivery.rejection_reason = f"Rejected by {previous_rider.username}: {reason_str}"
        delivery.save(update_fields=['rider', 'status', 'rejection_reason', 'updated_at'])

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=Delivery.DeliveryStatus.ASSIGNED,
            to_status=Delivery.DeliveryStatus.PENDING_ASSIGNMENT,
            changed_by=rider_user,
            comment=f"Assignment rejected: {reason_str}",
        )

        # Notify management staff
        management_users = User.objects.filter(role__in=['OWNER', 'MANAGER', 'STAFF'], is_active=True)
        for mgr in management_users[:5]:
            try:
                NotificationService.create_notification(
                    recipient=mgr,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Assignment Rejected",
                    message=f"Rider {rider_user.get_full_name() or rider_user.username} rejected Order {delivery.order.order_number}. Reason: {reason_str}",
                    priority=Notification.Priority.HIGH,
                    related_object=delivery,
                    action_url=f"/deliveries/{delivery.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def confirm_pickup(cls, delivery, rider_user):
        """
        Rider confirms pickup from shop/store.
        Moves status to IN_TRANSIT, generates secure OTP, and dispatches OTP to customer.
        """
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.rider != rider_user:
            raise PermissionDenied("You can only confirm pickup for deliveries assigned to you.")

        if delivery.status not in [Delivery.DeliveryStatus.ACCEPTED, Delivery.DeliveryStatus.AWAITING_PICKUP]:
            raise ValidationError(f"Cannot confirm pickup from '{delivery.get_status_display()}' state.")

        delivery.status = Delivery.DeliveryStatus.IN_TRANSIT
        delivery.picked_up_at = timezone.now()
        delivery.save(update_fields=['status', 'picked_up_at', 'updated_at'])

        # Generate secure expiring 6-digit OTP
        otp_code = cls.generate_and_store_otp(delivery)

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=Delivery.DeliveryStatus.ACCEPTED,
            to_status=Delivery.DeliveryStatus.IN_TRANSIT,
            changed_by=rider_user,
            comment=f"Picked up from store by rider. En route to customer. OTP dispatched.",
        )

        # Notify customer with OTP code
        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Package Picked Up - Out for Delivery",
                    message=(
                        f"Your order {delivery.order.order_number} is out for delivery with rider "
                        f"{rider_user.get_full_name() or 'your rider'}. "
                        f"Please provide this Delivery Confirmation PIN to the rider upon delivery: {otp_code}"
                    ),
                    priority=Notification.Priority.URGENT,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    def generate_and_store_otp(cls, delivery):
        """Generate a random 6-digit PIN and store its hash on the delivery."""
        otp_raw = str(secrets.randbelow(900000) + 100000)
        settings_obj = DeliverySetting.get_settings()
        expiry_minutes = settings_obj.otp_expiry_minutes or 60

        delivery.max_otp_attempts = settings_obj.max_otp_attempts or 5
        delivery.set_otp(otp_raw, expiry_minutes=expiry_minutes)
        delivery.save(update_fields=['max_otp_attempts', 'updated_at'])
        return otp_raw

    @classmethod
    @transaction.atomic
    def verify_delivery_otp(cls, delivery, otp_candidate, rider_user, recipient_name='', notes=''):
        """
        Rider submits customer OTP to verify delivery completion.
        Validates hash, attempt counts, and expiration.
        """
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.rider != rider_user:
            raise PermissionDenied("You can only complete deliveries assigned to you.")

        if delivery.status != Delivery.DeliveryStatus.IN_TRANSIT:
            raise ValidationError(f"Cannot complete delivery that is in '{delivery.get_status_display()}' state.")

        if delivery.otp_attempts >= delivery.max_otp_attempts:
            raise ValidationError("Maximum OTP verification attempts exceeded. Please contact store management.")

        if delivery.otp_expires_at and timezone.now() > delivery.otp_expires_at:
            raise ValidationError("Delivery confirmation OTP has expired. Please ask store management to regenerate or override.")

        # Check hash
        if not delivery.verify_otp_code(otp_candidate):
            delivery.otp_attempts += 1
            delivery.save(update_fields=['otp_attempts', 'updated_at'])
            remaining = max(delivery.max_otp_attempts - delivery.otp_attempts, 0)
            return {'success': False, 'message': f"Incorrect delivery PIN. Please ask customer for correct 6-digit code ({remaining} attempts remaining).", 'attempts_remaining': remaining}

        # Success! Mark as Delivered
        delivery.status = Delivery.DeliveryStatus.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.otp_verified_at = timezone.now()
        delivery.pod_method = Delivery.PodMethod.OTP
        delivery.pod_recipient_name = (recipient_name or delivery.customer_name or '').strip()
        delivery.pod_notes = notes.strip()
        delivery.pod_verified_by = rider_user
        delivery.save()
        DeliveryAssignment.objects.filter(delivery=delivery, rider=rider_user, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.COMPLETED, ended_at=timezone.now())

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=Delivery.DeliveryStatus.IN_TRANSIT,
            to_status=Delivery.DeliveryStatus.DELIVERED,
            changed_by=rider_user,
            comment=f"Delivery confirmed via customer OTP. Received by: {delivery.pod_recipient_name or 'Customer'}",
        )

        # Notify customer
        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Order Delivered Successfully",
                    message=f"Order {delivery.order.order_number} has been delivered. Thank you for shopping with MADAM HY!",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        # Notify management
        management_users = User.objects.filter(role__in=['OWNER', 'MANAGER'], is_active=True)
        for mgr in management_users[:3]:
            try:
                NotificationService.create_notification(
                    recipient=mgr,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Completed",
                    message=f"Order {delivery.order.order_number} was successfully delivered by {rider_user.get_full_name() or rider_user.username}.",
                    priority=Notification.Priority.LOW,
                    related_object=delivery,
                    action_url=f"/deliveries/{delivery.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def management_override_pod(cls, delivery, manager_user, reason, recipient_name='', notes=''):
        """Authorized management override when OTP is inaccessible."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if manager_user.role not in ['OWNER', 'MANAGER', 'STAFF']:
            raise PermissionDenied("Only management users can perform POD override.")

        if not DeliverySetting.get_settings().allow_management_override:
            raise PermissionDenied("Management proof-of-delivery override is disabled in delivery settings.")

        if delivery.status != Delivery.DeliveryStatus.IN_TRANSIT:
            raise ValidationError("Management confirmation is allowed only for an in-transit delivery.")

        if not reason or not str(reason).strip():
            raise ValidationError({'reason': 'A management override reason is required.'})

        previous_status = delivery.status
        delivery.status = Delivery.DeliveryStatus.DELIVERED
        delivery.delivered_at = timezone.now()
        delivery.pod_method = Delivery.PodMethod.MANAGEMENT_OVERRIDE
        delivery.pod_recipient_name = (recipient_name or delivery.customer_name or '').strip()
        delivery.pod_notes = f"Management Override by {manager_user.username}: {reason}. {notes}".strip()
        delivery.pod_verified_by = manager_user
        delivery.save()
        DeliveryAssignment.objects.filter(delivery=delivery, rider=delivery.rider, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.COMPLETED, ended_at=timezone.now())
        DeliveryAssignment.objects.filter(delivery=delivery, rider=delivery.rider, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.COMPLETED, ended_at=timezone.now())

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=previous_status,
            to_status=Delivery.DeliveryStatus.DELIVERED,
            changed_by=manager_user,
            comment=f"POD Override approved: {reason}",
        )

        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Order Marked as Delivered",
                    message=f"Your delivery for Order {delivery.order.order_number} has been confirmed by store management.",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=manager_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def report_delivery_failure(cls, delivery, rider_user, failure_reason, failure_note=''):
        """Rider reports an issue or failure during delivery attempt."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if delivery.rider != rider_user and rider_user.role not in ['OWNER', 'MANAGER']:
            raise PermissionDenied("Only the assigned rider or management can report delivery failure.")

        if delivery.status not in [Delivery.DeliveryStatus.IN_TRANSIT, Delivery.DeliveryStatus.ACCEPTED, Delivery.DeliveryStatus.ASSIGNED]:
            raise ValidationError(f"Cannot report delivery failure from '{delivery.get_status_display()}' state.")

        if not failure_reason:
            raise ValidationError({'failure_reason': 'A failure reason must be selected.'})
        if failure_reason not in dict(Delivery.FailureReason.choices):
            raise ValidationError({'failure_reason': 'Select a valid failure reason.'})

        delivery.status = Delivery.DeliveryStatus.FAILED
        delivery.failure_reason = failure_reason
        delivery.failure_note = (failure_note or '').strip()
        delivery.save()
        DeliveryAssignment.objects.filter(delivery=delivery, rider=delivery.rider, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.CANCELLED, ended_at=timezone.now(), reason=delivery.failure_note or delivery.get_failure_reason_display())

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=Delivery.DeliveryStatus.IN_TRANSIT,
            to_status=Delivery.DeliveryStatus.FAILED,
            changed_by=rider_user,
            comment=f"Delivery failed: {delivery.get_failure_reason_display()}. Note: {delivery.failure_note}",
        )

        # Notify management
        management_users = User.objects.filter(role__in=['OWNER', 'MANAGER', 'STAFF'], is_active=True)
        for mgr in management_users[:5]:
            try:
                NotificationService.create_notification(
                    recipient=mgr,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Attempt Failed",
                    message=f"Delivery for Order {delivery.order.order_number} failed. Reason: {delivery.get_failure_reason_display()}. Rider: {rider_user.username}",
                    priority=Notification.Priority.HIGH,
                    related_object=delivery,
                    action_url=f"/deliveries/{delivery.id}/",
                    actor=rider_user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def reschedule_delivery(cls, delivery, user, new_date, reason=''):
        """Reschedule a failed or pending delivery."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        if user.role not in ['OWNER', 'MANAGER', 'STAFF', 'RIDER']:
            raise PermissionDenied("Unauthorized to reschedule delivery.")

        previous_status = delivery.status
        delivery.rescheduled_date = new_date
        delivery.status = Delivery.DeliveryStatus.PENDING_ASSIGNMENT if not delivery.rider else Delivery.DeliveryStatus.ACCEPTED
        delivery.save()

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=previous_status,
            to_status=delivery.status,
            changed_by=user,
            comment=f"Delivery rescheduled to {new_date}. Reason: {reason or 'Customer request / rescheduling'}",
        )

        if delivery.order.customer:
            try:
                NotificationService.create_notification(
                    recipient=delivery.order.customer,
                    notification_type=Notification.NotificationType.ORDER,
                    title="Delivery Rescheduled",
                    message=f"Your delivery for Order {delivery.order.order_number} has been rescheduled to {new_date}.",
                    priority=Notification.Priority.NORMAL,
                    related_object=delivery,
                    action_url=f"/customer/orders/{delivery.order.id}/",
                    actor=user,
                )
            except Exception:
                pass

        return delivery

    @classmethod
    @transaction.atomic
    def return_delivery(cls, delivery, user, reason=''):
        """Mark items returned to store/warehouse."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        previous_status = delivery.status
        delivery.status = Delivery.DeliveryStatus.RETURNED
        delivery.save(update_fields=['status', 'updated_at'])
        DeliveryAssignment.objects.filter(delivery=delivery, rider=delivery.rider, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.CANCELLED, ended_at=timezone.now(), reason=reason or 'Package returned')

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=previous_status,
            to_status=Delivery.DeliveryStatus.RETURNED,
            changed_by=user,
            comment=f"Package returned to shop/store. Reason: {reason or 'Customer return / unfulfillable'}",
        )
        return delivery

    @classmethod
    @transaction.atomic
    def cancel_delivery(cls, delivery, user, reason=''):
        """Cancel a delivery job."""
        delivery = Delivery.objects.select_for_update().get(pk=delivery.pk)

        previous_status = delivery.status
        delivery.status = Delivery.DeliveryStatus.CANCELLED
        delivery.save(update_fields=['status', 'updated_at'])
        DeliveryAssignment.objects.filter(delivery=delivery, rider=delivery.rider, status__in=[DeliveryAssignment.AssignmentStatus.ASSIGNED, DeliveryAssignment.AssignmentStatus.ACCEPTED]).update(status=DeliveryAssignment.AssignmentStatus.CANCELLED, ended_at=timezone.now(), reason=reason or 'Delivery cancelled')

        DeliveryStatusHistory.objects.create(
            delivery=delivery,
            from_status=previous_status,
            to_status=Delivery.DeliveryStatus.CANCELLED,
            changed_by=user,
            comment=f"Delivery cancelled: {reason or 'Cancelled by user/management'}",
        )
        return delivery

    @classmethod
    @transaction.atomic
    def create_rider_account(cls, data, created_by=None):
        """Create a new user with RIDER role and associated RiderProfile."""
        email = (data.get('email') or '').strip().lower()
        username = (data.get('username') or '').strip()
        first_name = (data.get('first_name') or '').strip()
        last_name = (data.get('last_name') or '').strip()
        password = data.get('password') or ''
        phone_number = (data.get('phone_number') or '').strip()

        if not email:
            raise ValidationError({'email': 'Email address is required for rider.'})
        if not password:
            raise ValidationError({'password': 'An initial password is required for a rider account.'})
        validate_password(password)
        if not username:
            username = email.split('@')[0]

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({'email': 'A user with this email already exists.'})
        if User.objects.filter(username__iexact=username).exists():
            username = f"{username}_{secrets.token_hex(2)}"

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role='RIDER',
            is_active=bool(data.get('is_active', True)),
        )

        vehicle_type = data.get('vehicle_type') or RiderProfile.VehicleType.MOTORCYCLE
        profile = RiderProfile.objects.create(
            user=user,
            vehicle_type=vehicle_type,
            vehicle_number=(data.get('vehicle_number') or '').strip(),
            license_number=(data.get('license_number') or '').strip(),
            phone_number=phone_number,
            emergency_contact_name=(data.get('emergency_contact_name') or '').strip(),
            emergency_contact_phone=(data.get('emergency_contact_phone') or '').strip(),
            address=(data.get('address') or '').strip(),
            is_available=bool(data.get('is_available', True)),
            max_active_deliveries=int(data.get('max_active_deliveries') or 3),
            notes=(data.get('notes') or '').strip(),
        )

        return user, profile

    @classmethod
    def get_rider_dashboard_data(cls, rider_user):
        """Aggregate operational metrics for the authenticated rider."""
        profile = getattr(rider_user, 'rider_profile', None)

        qs = Delivery.objects.filter(rider=rider_user)

        new_assignments = qs.filter(status=Delivery.DeliveryStatus.ASSIGNED)
        pending_pickups = qs.filter(status=Delivery.DeliveryStatus.ACCEPTED)
        active_deliveries = qs.filter(status=Delivery.DeliveryStatus.IN_TRANSIT)
        completed_deliveries = qs.filter(status=Delivery.DeliveryStatus.DELIVERED)
        failed_deliveries = qs.filter(status=Delivery.DeliveryStatus.FAILED)

        recent_activity = qs.order_by('-updated_at')[:8]

        return {
            'rider': rider_user,
            'profile': profile,
            'is_available': profile.is_available if profile else False,
            'new_assignments_count': new_assignments.count(),
            'pending_pickups_count': pending_pickups.count(),
            'active_deliveries_count': active_deliveries.count(),
            'completed_count': completed_deliveries.count(),
            'failed_count': failed_deliveries.count(),
            'new_assignments': new_assignments[:5],
            'pending_pickups': pending_pickups[:5],
            'active_deliveries': active_deliveries[:5],
            'recent_activity': recent_activity,
        }

    @classmethod
    def get_management_dashboard_data(cls):
        """Aggregate business delivery metrics for store managers."""
        all_deliveries = Delivery.objects.all()

        unassigned_count = all_deliveries.filter(status=Delivery.DeliveryStatus.PENDING_ASSIGNMENT).count()
        assigned_count = all_deliveries.filter(status=Delivery.DeliveryStatus.ASSIGNED).count()
        in_transit_count = all_deliveries.filter(status=Delivery.DeliveryStatus.IN_TRANSIT).count()
        completed_count = all_deliveries.filter(status=Delivery.DeliveryStatus.DELIVERED).count()
        failed_count = all_deliveries.filter(status=Delivery.DeliveryStatus.FAILED).count()
        returned_count = all_deliveries.filter(status=Delivery.DeliveryStatus.RETURNED).count()

        total_count = all_deliveries.count()
        success_rate = (completed_count / total_count * 100) if total_count > 0 else 0.0

        riders_qs = RiderProfile.objects.select_related('user').all()
        active_riders_count = riders_qs.filter(is_available=True, user__is_active=True).count()
        total_riders_count = riders_qs.count()

        active_feed = all_deliveries.filter(
            status__in=[
                Delivery.DeliveryStatus.PENDING_ASSIGNMENT,
                Delivery.DeliveryStatus.ASSIGNED,
                Delivery.DeliveryStatus.ACCEPTED,
                Delivery.DeliveryStatus.IN_TRANSIT,
            ]
        ).select_related('order', 'rider', 'zone').order_by('-created_at')[:10]

        return {
            'total_deliveries': total_count,
            'unassigned_count': unassigned_count,
            'assigned_count': assigned_count,
            'in_transit_count': in_transit_count,
            'completed_count': completed_count,
            'failed_count': failed_count,
            'returned_count': returned_count,
            'success_rate': round(success_rate, 1),
            'active_riders_count': active_riders_count,
            'total_riders_count': total_riders_count,
            'active_feed': active_feed,
            'zones_count': DeliveryZone.objects.filter(is_active=True).count(),
        }
