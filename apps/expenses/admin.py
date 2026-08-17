from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        'expense_reference',
        'category',
        'vendor',
        'formatted_amount',
        'expense_date',
        'payment_method',
        'recorded_by',
        'created_at',
    )
    search_fields = (
        'expense_reference',
        'vendor',
        'description',
        'payment_reference',
        'notes',
    )
    list_filter = (
        'category',
        'payment_method',
        'expense_date',
        'recorded_by',
    )
    ordering = ('-expense_date', '-created_at')
    readonly_fields = ('created_at', 'updated_at')

    def formatted_amount(self, obj):
        return format_html('₦ {:,.2f}', obj.amount)

    formatted_amount.short_description = 'Amount'

    def delete_model(self, request, obj):
        raise ValidationError('Historical expense records cannot be deleted. Preserve the record.')

    def delete_queryset(self, request, queryset):
        raise ValidationError('Historical expense records cannot be deleted in bulk. Preserve the record.')
