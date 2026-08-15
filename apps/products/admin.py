from django.contrib import admin

from .models import Product, ProductCategory, ProductImage, ProductPriceHistory


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'selling_price', 'cost_price', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('name', 'sku', 'slug', 'description')
    list_editable = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('name',)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image', 'display_order', 'is_primary', 'created_at')
    list_filter = ('product', 'is_primary')
    search_fields = ('product__name', 'alt_text')
    ordering = ('product', 'display_order')


@admin.register(ProductPriceHistory)
class ProductPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'previous_price', 'new_price', 'changed_by', 'changed_at')
    list_filter = ('product', 'changed_by', 'changed_at')
    search_fields = ('product__name', 'reason', 'changed_by__email')
    readonly_fields = ('previous_price', 'new_price', 'changed_by', 'reason', 'changed_at')
    ordering = ('-changed_at',)
