from django.contrib import admin
from django.utils.html import format_html

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin interface for payment transaction records."""

    list_display = (
        'payment_reference',
        'transaction_type_display',
        'payment_method',
        'payment_status_display',
        'amount_display',
        'customer_display',
        'cashier_display',
        'created_at',
    )
    list_filter = ('payment_method', 'payment_status', 'created_at')
    search_fields = (
        'payment_reference',
        'transaction_reference',
        'notes',
        'customer__first_name',
        'customer__last_name',
        'cashier__first_name',
        'cashier__last_name',
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Payment Details', {
            'fields': (
                'payment_reference',
                'amount',
                'payment_method',
                'payment_status',
                'transaction_reference',
                'transaction_metadata',
                'notes',
            )
        }),
        ('Transaction Context', {
            'fields': ('sale', 'order', 'customer', 'cashier'),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def transaction_type_display(self, obj):
        if obj.sale:
            return 'Sale'
        if obj.order:
            return 'Order'
        return 'Unassigned'

    transaction_type_display.short_description = 'Transaction'

    def payment_status_display(self, obj):
        colors = {
            'PENDING': '#FFA500',
            'COMPLETED': '#228B22',
            'FAILED': '#DC143C',
            'REFUNDED': '#6C757D',
        }
        color = colors.get(obj.payment_status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_payment_status_display(),
        )

    payment_status_display.short_description = 'Status'

    def amount_display(self, obj):
        return f'₦ {obj.amount:,.2f}'

    amount_display.short_description = 'Amount'

    def customer_display(self, obj):
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}".strip() or obj.customer.email
        return '—'

    customer_display.short_description = 'Customer'

    def cashier_display(self, obj):
        if obj.cashier:
            return f"{obj.cashier.first_name} {obj.cashier.last_name}".strip() or obj.cashier.email
        return '—'

    cashier_display.short_description = 'Cashier'

    def has_delete_permission(self, request, obj=None):
        if obj and obj.payment_status in ['COMPLETED', 'REFUNDED']:
            return False
        return True

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj and obj.payment_status in ['COMPLETED', 'REFUNDED']:
            readonly.extend(['amount', 'payment_method', 'payment_status', 'transaction_reference', 'sale', 'order', 'customer', 'cashier'])
        return readonly
