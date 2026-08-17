from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Request


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_number',
        'customer',
        'request_type',
        'title',
        'priority',
        'status',
        'assigned_to',
        'created_at',
        'updated_at',
        'resolved_at',
    )
    search_fields = (
        'request_number',
        'title',
        'description',
        'resolution',
        'customer__email',
        'customer__first_name',
        'customer__last_name',
        'assigned_to__email',
    )
    list_filter = (
        'status',
        'priority',
        'request_type',
        'created_at',
        'customer',
        'assigned_to',
    )
    ordering = ('-updated_at', '-created_at')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')

    def delete_model(self, request, obj):
        raise ValidationError('Historical request records cannot be deleted. Preserve the request record.')

    def delete_queryset(self, request, queryset):
        raise ValidationError('Historical request records cannot be deleted in bulk. Preserve the request records.')
