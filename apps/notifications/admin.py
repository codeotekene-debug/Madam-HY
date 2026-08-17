from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'priority', 'is_read', 'title', 'created_at')
    list_filter = ('notification_type', 'priority', 'is_read')
    search_fields = ('recipient__email', 'recipient__username', 'title', 'message')
    readonly_fields = ('created_at', 'updated_at', 'read_at')
    ordering = ('-created_at',)
    list_select_related = ('recipient',)

    def has_delete_permission(self, request, obj=None):
        return False
