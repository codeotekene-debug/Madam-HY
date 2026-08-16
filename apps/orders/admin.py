from django.contrib import admin
from django.utils.html import format_html

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    """Inline display of OrderItems within Order admin."""

    model = OrderItem
    readonly_fields = (
        'product',
        'product_name_snapshot',
        'sku_snapshot',
        'quantity',
        'unit_price',
        'line_total_display',
        'created_at',
    )
    can_delete = False
    fields = (
        'product',
        'product_name_snapshot',
        'sku_snapshot',
        'quantity',
        'unit_price',
        'line_total_display',
        'created_at',
    )
    extra = 0

    def line_total_display(self, obj):
        """Display calculated line total."""
        if obj:
            return f'₦ {obj.line_total:,.2f}'
        return '-'

    line_total_display.short_description = 'Line Total'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order management."""

    list_display = (
        'order_number',
        'customer_display',
        'status_display',
        'payment_method',
        'payment_status_display',
        'total_display',
        'created_at_display',
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('order_number', 'customer__first_name', 'customer__last_name', 'created_by__first_name', 'created_by__last_name', 'notes')
    readonly_fields = (
        'order_number',
        'subtotal',
        'total',
        'created_at',
        'updated_at',
    )
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'status', 'customer', 'created_by', 'created_at', 'updated_at'),
        }),
        ('Order Items & Totals', {
            'fields': ('subtotal', 'discount', 'total'),
        }),
        ('Payment', {
            'fields': ('payment_method', 'payment_status'),
        }),
        ('Delivery & Contact', {
            'fields': ('delivery_address', 'customer_phone'),
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
    )

    def status_display(self, obj):
        """Display status with color coding."""
        status_colors = {
            'PENDING': '#FFA500',      # Orange
            'CONFIRMED': '#4169E1',    # Blue
            'PROCESSING': '#8B008B',   # Purple
            'READY': '#228B22',        # Green
            'COMPLETED': '#006400',    # Dark Green
            'CANCELLED': '#DC143C',    # Crimson
        }
        color = status_colors.get(obj.status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_display.short_description = 'Status'

    def payment_status_display(self, obj):
        """Display payment status with color coding."""
        payment_colors = {
            'PENDING': '#FFA500',    # Orange
            'CONFIRMED': '#228B22',  # Green
            'FAILED': '#DC143C',     # Crimson
        }
        color = payment_colors.get(obj.payment_status, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_payment_status_display()
        )

    payment_status_display.short_description = 'Payment Status'

    def customer_display(self, obj):
        """Display customer name or 'No Customer'."""
        if obj.customer:
            return f"{obj.customer.first_name} {obj.customer.last_name}".strip() or obj.customer.email
        return 'No Customer'

    customer_display.short_description = 'Customer'

    def total_display(self, obj):
        """Display total with currency formatting."""
        return f'₦ {obj.total:,.2f}'

    total_display.short_description = 'Total'

    def created_at_display(self, obj):
        """Display created_at in user-friendly format."""
        return obj.created_at.strftime('%d %b %Y %H:%M')

    created_at_display.short_description = 'Created'

    def has_add_permission(self, request):
        """Allow orders to be created only through views, not admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of orders to preserve historical data."""
        return False

    def get_readonly_fields(self, request, obj=None):
        """Make fields readonly for completed or cancelled orders."""
        readonly = list(self.readonly_fields)
        if obj and obj.status in ['COMPLETED', 'CANCELLED']:
            readonly.extend(['status', 'payment_method', 'payment_status', 'discount', 'customer', 'created_by'])
        return readonly

