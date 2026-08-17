from django.contrib import admin

from apps.activity_logs.models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('actor', 'action_type', 'action_label', 'content_object', 'created_at')
    list_filter = ('action_type', 'content_type')
    search_fields = ('actor__email', 'actor__username', 'action_label', 'description')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    list_select_related = ('actor', 'content_type')

    def content_object(self, obj):
        return obj.related_object if obj.content_type_id and obj.object_id else '-'

    content_object.short_description = 'Related Object'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
