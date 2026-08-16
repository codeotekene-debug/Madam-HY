from django.contrib import admin

from .models import InventoryItem, StockMovement


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'reorder_level', 'stock_status', 'is_active', 'updated_at')
    list_filter = ('is_active', 'updated_at')
    search_fields = ('product__name', 'product__sku')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('product__name',)

    @admin.display(description='Reorder level')
    def reorder_level(self, obj):
        return obj.product.reorder_level

    @admin.display(description='Stock status')
    def stock_status(self, obj):
        return obj.stock_status


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'movement_type', 'quantity', 'previous_quantity', 'new_quantity', 'reason', 'reference', 'created_by', 'created_at')
    list_filter = ('movement_type', 'created_at', 'product')
    search_fields = ('product__name', 'reference', 'reason', 'created_by__email')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
