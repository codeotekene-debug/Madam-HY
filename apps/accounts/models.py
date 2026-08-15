from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


# Role choices for the User model
ROLE_CHOICES = [
    ('OWNER', _('Owner')),
    ('MANAGER', _('Manager')),
    ('CASHIER', _('Cashier')),
    ('STAFF', _('Staff')),
    ('CUSTOMER', _('Customer')),
]


class User(AbstractUser):
    """
    Custom User model for MADAM HY.

    Extends Django's AbstractUser to add:
    - Role-based access control
    - Phone number
    - Timestamps

    Users can authenticate with email or username.
    """

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
