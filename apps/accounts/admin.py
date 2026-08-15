from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, CustomerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom User Admin for MADAM HY.

    Extends Django's default UserAdmin to support the custom User model
    with email as the primary auth field and role-based access.
    """

    # Fieldsets for add (create) form
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        (_('Personal info'), {
            'fields': ('first_name', 'last_name', 'phone_number'),
        }),
        (_('Role & Permissions'), {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )

    # Fieldsets for change (edit) form
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {
            'fields': ('first_name', 'last_name', 'phone_number', 'username'),
        }),
        (_('Role & Permissions'), {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {
            'fields': ('last_login', 'created_at', 'updated_at'),
        }),
    )

    # List display
    list_display = ('email', 'get_full_name', 'role', 'is_active', 'is_staff', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'username', 'phone_number')
    ordering = ('-created_at',)

    # Read-only fields
    readonly_fields = ('created_at', 'updated_at', 'last_login')

    # Filter by role as default
    def get_queryset(self, request):
        """Allow filtering users by role."""
        qs = super().get_queryset(request)
        return qs.select_related('customer_profile')

    def get_full_name(self, obj):
        """Display full name in list."""
        return obj.get_full_name()
    get_full_name.short_description = _('Full Name')


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    """
    Admin for CustomerProfile.

    Allows managing customer-specific information separate from auth.
    """

    fieldsets = (
        (None, {
            'fields': ('user',),
        }),
        (_('Contact Information'), {
            'fields': ('address', 'city', 'state', 'postal_code'),
        }),
        (_('Preferences'), {
            'fields': ('preferred_payment_method', 'notes'),
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    list_display = ('get_email', 'get_full_name', 'city', 'created_at')
    list_filter = ('created_at', 'city')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'city')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

    def get_email(self, obj):
        """Display user email."""
        return obj.user.email
    get_email.short_description = _('Email')

    def get_full_name(self, obj):
        """Display user full name."""
        return obj.user.get_full_name()
    get_full_name.short_description = _('Full Name')
