from decimal import Decimal
import hashlib
import hmac
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class DeliveryZone(models.Model):
    """Configurable delivery zone and associated pricing."""

    name = models.CharField(
        _('zone name'),
        max_length=120,
        unique=True,
        help_text=_('Descriptive name of the zone (e.g., Victoria Island, Lekki Phase 1, Ikeja).'),
    )
    code = models.CharField(
        _('zone code'),
        max_length=50,
        unique=True,
        help_text=_('Short code for zone identification (e.g., VI-01, LEK-01).'),
    )
    fee = models.DecimalField(
        _('delivery fee'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('Standard delivery fee charged to customer orders in this zone.'),
    )
    description = models.TextField(
        _('description'),
        blank=True,
        help_text=_('Areas, landmarks, and estates included in this zone.'),
    )
    estimated_delivery_time = models.CharField(
        _('estimated delivery time'),
        max_length=80,
        blank=True,
        default='30-60 minutes',
        help_text=_('Expected delivery timeframe (e.g., 30-45 mins, Same Day).'),
    )
    is_active = models.BooleanField(
        _('is active'),
        default=True,
        help_text=_('Whether this delivery zone is active for customer checkout.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Delivery Zone')
        verbose_name_plural = _('Delivery Zones')

    def __str__(self):
        return f"{self.name} (₦{self.fee:,.2f})"

    def clean(self):
        super().clean()
        if self.fee is not None and self.fee < 0:
            raise ValidationError({'fee': _('Delivery fee cannot be negative.')})
        if not self.code:
            # Generate code from name if empty
            base_code = ''.join(c.upper() for c in self.name if c.isalnum())[:10]
            self.code = f"ZONE-{base_code}" if base_code else "ZONE-01"


class RiderProfile(models.Model):
    """Rider profile information and operational availability."""

    class VehicleType(models.TextChoices):
        MOTORCYCLE = 'MOTORCYCLE', _('Motorcycle')
        BICYCLE = 'BICYCLE', _('Bicycle')
        SCOOTER = 'SCOOTER', _('Scooter')
        CAR = 'CAR', _('Car')
        VAN = 'VAN', _('Delivery Van')
        ON_FOOT = 'ON_FOOT', _('On Foot / Walking')

    class RiderStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', _('Available')
        ON_DELIVERY = 'ON_DELIVERY', _('On Delivery')
        OFFLINE = 'OFFLINE', _('Offline')
        SUSPENDED = 'SUSPENDED', _('Suspended')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rider_profile',
        limit_choices_to={'role': 'RIDER'},
        help_text=_('User account with RIDER role.'),
    )
    vehicle_type = models.CharField(
        _('vehicle type'),
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.MOTORCYCLE,
    )
    vehicle_number = models.CharField(
        _('vehicle registration / plate number'),
        max_length=50,
        blank=True,
    )
    license_number = models.CharField(
        _('driver / rider license number'),
        max_length=80,
        blank=True,
    )
    phone_number = models.CharField(
        _('phone number'),
        max_length=25,
        blank=True,
    )
    emergency_contact_name = models.CharField(
        _('emergency contact name'),
        max_length=120,
        blank=True,
    )
    emergency_contact_phone = models.CharField(
        _('emergency contact phone'),
        max_length=25,
        blank=True,
    )
    address = models.TextField(
        _('residential address'),
        blank=True,
    )
    is_available = models.BooleanField(
        _('is available'),
        default=True,
        help_text=_('Rider availability toggle for receiving new assignments.'),
    )
    status = models.CharField(
        _('operational status'),
        max_length=20,
        choices=RiderStatus.choices,
        default=RiderStatus.AVAILABLE,
    )
    max_active_deliveries = models.PositiveIntegerField(
        _('max active deliveries'),
        default=3,
        help_text=_('Maximum concurrent deliveries permitted for this rider.'),
    )
    notes = models.TextField(_('internal notes'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Rider Profile')
        verbose_name_plural = _('Rider Profiles')

    def __str__(self):
        return f"Rider: {self.user.get_full_name() or self.user.username} ({self.get_vehicle_type_display()})"

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != 'RIDER':
            raise ValidationError({'user': _('A rider profile can only belong to a RIDER account.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        return self.user.email

    @property
    def contact_phone(self):
        return self.phone_number or getattr(self.user, 'phone_number', '') or ''

    @property
    def active_deliveries_count(self):
        """Count active assigned/accepted/in-transit deliveries."""
        return self.user.assigned_deliveries.filter(
            status__in=['ASSIGNED', 'ACCEPTED', 'AWAITING_PICKUP', 'IN_TRANSIT']
        ).count()

    @property
    def completed_deliveries_count(self):
        return self.user.assigned_deliveries.filter(status='DELIVERED').count()

    @property
    def failed_deliveries_count(self):
        return self.user.assigned_deliveries.filter(status='FAILED').count()

    @property
    def can_accept_more(self):
        if not self.user.is_active or not self.is_available or self.status in ['OFFLINE', 'SUSPENDED']:
            return False
        return self.active_deliveries_count < self.max_active_deliveries


class Delivery(models.Model):
    """Core delivery lifecycle record linking orders, riders, and proof of delivery."""

    class DeliveryStatus(models.TextChoices):
        PENDING_ASSIGNMENT = 'PENDING_ASSIGNMENT', _('Pending Assignment')
        ASSIGNED = 'ASSIGNED', _('Assigned')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        AWAITING_PICKUP = 'AWAITING_PICKUP', _('Awaiting Pickup')
        IN_TRANSIT = 'IN_TRANSIT', _('In Transit')
        DELIVERED = 'DELIVERED', _('Delivered')
        FAILED = 'FAILED', _('Failed')
        RETURNED = 'RETURNED', _('Returned')
        CANCELLED = 'CANCELLED', _('Cancelled')

    class FailureReason(models.TextChoices):
        CUSTOMER_UNAVAILABLE = 'CUSTOMER_UNAVAILABLE', _('Customer Unavailable')
        INCORRECT_ADDRESS = 'INCORRECT_ADDRESS', _('Incorrect / Incomplete Address')
        CUSTOMER_UNREACHABLE = 'CUSTOMER_UNREACHABLE', _('Customer Unreachable by Phone')
        CUSTOMER_REFUSED = 'CUSTOMER_REFUSED', _('Customer Refused Delivery')
        VEHICLE_BREAKDOWN = 'VEHICLE_BREAKDOWN', _('Vehicle Breakdown / Mechanical Problem')
        OTHER = 'OTHER', _('Other Delivery Issue')

    class PodMethod(models.TextChoices):
        OTP = 'OTP', _('OTP Verification')
        MANAGEMENT_OVERRIDE = 'MANAGEMENT_OVERRIDE', _('Management Override')
        SIGNATURE = 'SIGNATURE', _('Direct Confirmation')

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='delivery',
        help_text=_('Order associated with this delivery job.'),
    )
    tracking_number = models.CharField(
        _('tracking number'),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_('Unique delivery tracking code (e.g., MH-DEL-10501).'),
    )
    rider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_deliveries',
        limit_choices_to={'role': 'RIDER'},
        help_text=_('Assigned delivery rider.'),
    )
    zone = models.ForeignKey(
        DeliveryZone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries',
        help_text=_('Delivery zone for destination.'),
    )
    delivery_fee = models.DecimalField(
        _('delivery fee'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    status = models.CharField(
        _('delivery status'),
        max_length=25,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING_ASSIGNMENT,
        db_index=True,
    )

    # Customer & destination details snapshot
    customer_name = models.CharField(_('customer name'), max_length=150, blank=True)
    customer_phone = models.CharField(_('customer phone'), max_length=30, blank=True)
    delivery_address = models.TextField(_('delivery address'))
    delivery_instructions = models.TextField(_('delivery instructions'), blank=True)

    # Lifecycle timestamps
    assigned_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)

    # Rejection & Failure fields
    rejection_reason = models.TextField(_('rejection reason'), blank=True)
    failure_reason = models.CharField(
        _('failure reason'),
        max_length=30,
        choices=FailureReason.choices,
        blank=True,
    )
    failure_note = models.TextField(_('failure note'), blank=True)
    rescheduled_date = models.DateTimeField(null=True, blank=True)

    # Proof of Delivery (OTP)
    otp_code_hash = models.CharField(
        _('OTP code hash'),
        max_length=128,
        blank=True,
        help_text=_('SHA-256 hash of the secure 6-digit confirmation code.'),
    )
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveIntegerField(default=0)
    max_otp_attempts = models.PositiveIntegerField(default=5)
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    pod_method = models.CharField(
        _('POD method'),
        max_length=25,
        choices=PodMethod.choices,
        default=PodMethod.OTP,
    )
    pod_recipient_name = models.CharField(_('recipient name'), max_length=150, blank=True)
    pod_notes = models.TextField(_('POD confirmation notes'), blank=True)
    pod_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_pod_deliveries',
        help_text=_('User who verified the delivery proof (rider or manager).'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Delivery')
        verbose_name_plural = _('Deliveries')
        indexes = [
            models.Index(fields=['tracking_number']),
            models.Index(fields=['status']),
            models.Index(fields=['rider', 'status']),
            models.Index(fields=['order']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Delivery {self.tracking_number} ({self.get_status_display()})"

    @staticmethod
    def hash_otp(code: str) -> str:
        """Securely hash an OTP string using SHA-256."""
        return hashlib.sha256(code.strip().encode('utf-8')).hexdigest()

    def set_otp(self, code: str, expiry_minutes: int = 60):
        """Set hashed OTP and expiry timestamp."""
        self.otp_code_hash = self.hash_otp(code)
        self.otp_expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        self.otp_attempts = 0
        self.save(update_fields=['otp_code_hash', 'otp_expires_at', 'otp_attempts', 'updated_at'])

    def verify_otp_code(self, candidate_code: str) -> bool:
        """Check if submitted code matches hash, is not expired, and under max attempts."""
        if not self.otp_code_hash:
            return False
        if self.otp_attempts >= self.max_otp_attempts:
            return False
        if self.otp_expires_at and timezone.now() > self.otp_expires_at:
            return False
        return hmac.compare_digest(self.hash_otp(candidate_code), self.otp_code_hash)

    @property
    def is_active(self):
        return self.status in [
            self.DeliveryStatus.ASSIGNED,
            self.DeliveryStatus.ACCEPTED,
            self.DeliveryStatus.AWAITING_PICKUP,
            self.DeliveryStatus.IN_TRANSIT,
        ]

    @property
    def is_delivered(self):
        return self.status == self.DeliveryStatus.DELIVERED

    @property
    def is_failed(self):
        return self.status == self.DeliveryStatus.FAILED


class DeliveryAssignment(models.Model):
    """Durable record of each rider assignment and its outcome."""

    class AssignmentStatus(models.TextChoices):
        ASSIGNED = 'ASSIGNED', _('Assigned')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        REJECTED = 'REJECTED', _('Rejected')
        REASSIGNED = 'REASSIGNED', _('Reassigned')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.PROTECT,
        related_name='assignments',
        help_text=_('Delivery associated with this assignment event.'),
    )
    rider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='delivery_assignment_history',
        limit_choices_to={'role': 'RIDER'},
        help_text=_('Rider selected for this assignment.'),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_assignments_created',
        help_text=_('Manager or dispatcher who made the assignment.'),
    )
    status = models.CharField(
        _('assignment outcome'),
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ASSIGNED,
        db_index=True,
    )
    reason = models.TextField(_('reason or notes'), blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-assigned_at']
        verbose_name = _('Delivery Assignment')
        verbose_name_plural = _('Delivery Assignments')
        indexes = [
            models.Index(fields=['delivery', '-assigned_at']),
            models.Index(fields=['rider', 'status', '-assigned_at']),
        ]

    def __str__(self):
        return f"{self.delivery.tracking_number} assigned to {self.rider.get_full_name() or self.rider.username}"

    def clean(self):
        super().clean()
        if self.rider_id and self.rider.role != 'RIDER':
            raise ValidationError({'rider': _('Only a RIDER account can receive a delivery assignment.')})
        if self.assigned_by_id and self.assigned_by.role not in {'OWNER', 'MANAGER', 'STAFF'}:
            raise ValidationError({'assigned_by': _('Only authorized delivery management can make an assignment.')})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DeliveryStatusHistory(models.Model):
    """Audit log of delivery status changes with actor and remarks."""

    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name='history',
        help_text=_('Delivery record this event belongs to.'),
    )
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivery_history_changes',
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Delivery Status History')
        verbose_name_plural = _('Delivery Status Histories')

    def __str__(self):
        return f"{self.delivery.tracking_number}: {self.from_status} -> {self.to_status} at {self.created_at}"


class DeliverySetting(models.Model):
    """System-wide delivery configuration parameters."""

    otp_expiry_minutes = models.PositiveIntegerField(
        _('OTP expiry time (minutes)'),
        default=60,
    )
    max_otp_attempts = models.PositiveIntegerField(
        _('Maximum OTP attempts'),
        default=5,
    )
    allow_management_override = models.BooleanField(
        _('Allow management override for POD'),
        default=True,
    )
    auto_assign_enabled = models.BooleanField(
        _('Enable automatic rider assignment'),
        default=False,
    )
    max_active_deliveries_per_rider = models.PositiveIntegerField(
        _('Default max deliveries per rider'),
        default=4,
    )
    support_phone = models.CharField(
        _('Delivery support phone line'),
        max_length=30,
        default='+234 800 MADAM HY',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Delivery Setting')
        verbose_name_plural = _('Delivery Settings')

    def __str__(self):
        return "Delivery Global Settings"

    @classmethod
    def get_settings(cls):
        """Retrieve or create singleton settings record."""
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
