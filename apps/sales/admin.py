from django.contrib import admin
from django.utils.html import format_html

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    """Inline admin for SaleItems within a Sale."""

    model = SaleItem
    extra = 0
    readonly_fields = (
        'product',
        'quantity',
        'unit_price',
        'discount',
        'line_total_display',
        'product_name_snapshot',
        'sku_snapshot',
        'created_at',
    )
    fields = (
        'product',
        'quantity',
        'unit_price',
        'discount',
        'line_total_display',
        'product_name_snapshot',
        'sku_snapshot',
    )
    can_delete = False

    def line_total_display(self, obj):
        """Display the calculated line total."""
        return f"₦ {obj.line_total:,.2f}"

    line_total_display.short_description = 'Line Total'


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Admin interface for Sales."""

    list_display = (
        'sale_number',
        'status_badge',
        'cashier',
        'customer_display',
        'payment_method',
        'total_display',
        'created_at_short',
    )
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at', 'cashier')
    search_fields = ('sale_number', 'customer__email', 'cashier__email', 'notes')
    readonly_fields = (
        'sale_number',
        'subtotal',
        'total',
        'created_at',
        'updated_at',
        'total_display',
        'subtotal_display',
        'discount_display',
    )
    fieldsets = (
        ('Sale Information', {
            'fields': ('sale_number', 'status', 'created_at', 'updated_at'),
        }),
        ('Parties', {
            'fields': ('customer', 'cashier'),
        }),
        ('Payment', {
            'fields': ('payment_method', 'payment_status', 'amount_received', 'change_amount'),
        }),
        ('Totals', {
            'fields': ('subtotal_display', 'discount', 'discount_display', 'total_display'),
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
    )
    inlines = [SaleItemInline]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    can_delete = False

    def get_readonly_fields(self, request, obj=None):
        """
        Make all fields readonly for completed or cancelled sales.
        Only sale_number, status, created_at, updated_at are always readonly.
        """
        readonly = list(self.readonly_fields)
        if obj and obj.status != obj.SaleStatus.DRAFT:
            readonly.extend(['customer', 'cashier', 'payment_method', 'payment_status', 'discount', 'notes', 'amount_received', 'change_amount'])
        return readonly

    def status_badge(self, obj):
        """Display status as a colored badge."""
        colors = {
            'DRAFT': '#FFA500',      # Orange
            'COMPLETED': '#28a745',  # Green
            'CANCELLED': '#dc3545',  # Red
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 0.9em;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = 'Status'

    def customer_display(self, obj):
        """Display customer name or 'Walk-in' if no customer."""
        if obj.customer:
            return obj.customer.get_full_name() or obj.customer.email
        return 'Walk-in'

    customer_display.short_description = 'Customer'

    def total_display(self, obj):
        """Display total with currency formatting."""
        return f"₦ {obj.total:,.2f}"

    total_display.short_description = 'Total'

    def subtotal_display(self, obj):
        """Display subtotal with currency formatting."""
        return f"₦ {obj.subtotal:,.2f}"

    subtotal_display.short_description = 'Subtotal'

    def discount_display(self, obj):
        """Display discount with currency formatting."""
        return f"₦ {obj.discount:,.2f}"

    discount_display.short_description = 'Discount'

    def created_at_short(self, obj):
        """Display created_at in short format."""
        return obj.created_at.strftime('%Y-%m-%d %H:%M')

    created_at_short.short_description = 'Created'


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    """Admin interface for Sale Items."""

    list_display = (
        'sale_number',
        'product_name_snapshot',
        'sku_snapshot',
        'quantity',
        'unit_price_display',
        'line_total_display',
    )
    list_filter = ('created_at', 'sale__status')
    search_fields = ('sale__sale_number', 'product__name', 'product__sku', 'product_name_snapshot', 'sku_snapshot')
    readonly_fields = (
        'sale',
        'product',
        'quantity',
        'unit_price',
        'discount',
        'product_name_snapshot',
        'sku_snapshot',
        'created_at',
        'line_total_display',
    )
    fields = (
        'sale',
        'product',
        'quantity',
        'unit_price',
        'discount',
        'line_total_display',
        'product_name_snapshot',
        'sku_snapshot',
        'created_at',
    )
    ordering = ['-created_at']
    can_delete = False

    def sale_number(self, obj):
        """Display the sale number."""
        return obj.sale.sale_number

    sale_number.short_description = 'Sale Number'

    def unit_price_display(self, obj):
        """Display unit price with currency formatting."""
        return f"₦ {obj.unit_price:,.2f}"

    unit_price_display.short_description = 'Unit Price'

    def line_total_display(self, obj):
        """Display line total with currency formatting."""
        return f"₦ {obj.line_total:,.2f}"

    line_total_display.short_description = 'Line Total'
