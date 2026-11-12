from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    OWNER = 'OWNER', _('Owner')
    MANAGER = 'MANAGER', _('Manager')
    CASHIER = 'CASHIER', _('Cashier')
    STAFF = 'STAFF', _('Staff')
    CUSTOMER = 'CUSTOMER', _('Customer')
    RIDER = 'RIDER', _('Rider')


# Role choices for the User model
ROLE_CHOICES = Role.choices


class User(AbstractUser):
    """
    Custom User model for MADAM HY.

    Extends Django's AbstractUser to add:
    - Role-based access control
    - Phone number
    - Timestamps

    Users can authenticate with email or username.
    """

    Role = Role
    ROLE_CHOICES = ROLE_CHOICES

    # Authentication
    email = models.EmailField(
        _('email address'),
        unique=True,
        help_text=_('Required. Email address must be unique.')
    )

    # Profile information
    phone_number = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^[\d\s\-\+\(\)]+$',
                message=_('Phone number must contain only digits, spaces, hyphens, and plus signs.'),
                code='invalid_phone'
            )
        ],
        help_text=_('Optional. Phone number for contact.')
    )

    # Role-based access
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=ROLE_CHOICES,
        default='CUSTOMER',
        help_text=_('User role determines access level and permissions.')
    )

    # Status
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_('Inactive users cannot log in.')
    )

    # Notification & communication preferences
    order_notifications = models.BooleanField(
        _('order notifications'),
        default=True,
        help_text=_('Receive notifications about order status changes.')
    )
    payment_notifications = models.BooleanField(
        _('payment notifications'),
        default=True,
        help_text=_('Receive reminders for credit payments.')
    )
    request_notifications = models.BooleanField(
        _('request notifications'),
        default=True,
        help_text=_('Receive updates on your product requests.')
    )
    promotion_notifications = models.BooleanField(
        _('promotion notifications'),
        default=False,
        help_text=_('Get notified about new products and special offers.')
    )
    preferences = models.JSONField(
        _('preferences'),
        default=dict,
        blank=True,
        help_text=_('User preferences including language, currency, marketing, and delivery options.')
    )

    # Timestamps
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    # Make email the unique identifier for authentication
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'auth_user'  # Keep Django admin happy
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"

    def get_full_name(self):
        """Return the user's full name."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.username

    def is_owner(self):
        """Check if user is an owner."""
        return self.role == 'OWNER'

    def is_manager(self):
        """Check if user is a manager."""
        return self.role == 'MANAGER'

    def is_cashier(self):
        """Check if user is a cashier."""
        return self.role == 'CASHIER'

    def is_staff_member(self):
        """Check if user is staff (non-cashier)."""
        return self.role == 'STAFF'

    def is_customer(self):
        """Check if user is a customer."""
        return self.role == 'CUSTOMER'

    def is_rider(self):
        """Check if user is a delivery rider."""
        return self.role == 'RIDER'

    @property
    def available_credit(self):
        """Return available credit allowance for customer, or Decimal('0.00')."""
        try:
            from decimal import Decimal
            account = getattr(self, 'credit_account', None)
            if account:
                return account.get_available_credit()
            return Decimal('0.00')
        except Exception:
            from decimal import Decimal
            return Decimal('0.00')

    def get_notification_preferences(self):
        """Return a dictionary of the user's notification preferences."""
        return {
            'order_notifications': bool(self.order_notifications),
            'payment_notifications': bool(self.payment_notifications),
            'request_notifications': bool(self.request_notifications),
            'promotion_notifications': bool(self.promotion_notifications),
            'orders': bool(self.order_notifications),
            'payments': bool(self.payment_notifications),
            'requests': bool(self.request_notifications),
            'promotions': bool(self.promotion_notifications),
        }

    def get_preferences(self):
        """Return structured preferences matching settings UI and API."""
        extra_prefs = self.preferences if isinstance(self.preferences, dict) else {}
        return {
            'notifications': {
                'orders': bool(self.order_notifications),
                'promotions': bool(self.promotion_notifications),
                'requests': bool(self.request_notifications),
                'payments': bool(self.payment_notifications),
            },
            'preferences': {
                'language': str(extra_prefs.get('language', 'en')),
                'currency': str(extra_prefs.get('currency', 'NGN')),
                'marketing': bool(extra_prefs.get('marketing', False)),
            },
            'delivery': {
                'preferredMethod': str(extra_prefs.get('preferred_delivery', 'Delivery')),
            },
        }


class CustomerProfile(models.Model):
    """
    Customer-specific profile information.

    Separates customer data from authentication.
    Only populated for users with role='CUSTOMER'.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text=_('Link to the customer user account.')
    )

    # Contact information
    address = models.TextField(
        _('address'),
        blank=True,
        help_text=_('Customer delivery address.')
    )

    city = models.CharField(
        _('city'),
        max_length=100,
        blank=True,
        help_text=_('City of residence.')
    )

    state = models.CharField(
        _('state'),
        max_length=100,
        blank=True,
        help_text=_('State/Province of residence.')
    )

    postal_code = models.CharField(
        _('postal code'),
        max_length=20,
        blank=True,
        help_text=_('Postal code.')
    )

    # Customer preferences and status
    preferred_payment_method = models.CharField(
        _('preferred payment method'),
        max_length=20,
        blank=True,
        help_text=_('Customer preferred way to pay.')
    )

    notes = models.TextField(
        _('notes'),
        blank=True,
        help_text=_('Internal notes about the customer.')
    )

    # Audit trail
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('customer profile')
        verbose_name_plural = _('customer profiles')
        ordering = ['-created_at']

    def __str__(self):
        return f"Profile: {self.user.get_full_name()}"

    @staticmethod
    def create_for_customer(user):
        """
        Create a CustomerProfile for a new customer user.

        Args:
            user: A User instance with role='CUSTOMER'

        Returns:
            CustomerProfile instance

        Raises:
            ValueError: If user is not a customer
        """
        if user.role != 'CUSTOMER':
            raise ValueError("CustomerProfile can only be created for CUSTOMER role users.")

        profile, created = CustomerProfile.objects.get_or_create(user=user)
        return profile
