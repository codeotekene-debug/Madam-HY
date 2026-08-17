from django.contrib import admin

from .models import CreditAccount, CreditTransaction


@admin.register(CreditAccount)
class CreditAccountAdmin(admin.ModelAdmin):
    list_display = (
        'customer_display',
        'credit_limit_display',
        'outstanding_balance_display',
        'status',
        'approved_by_display',
        'next_due_date',
        'last_payment_date',
        'created_at',
    )
    list_filter = ('status', 'approved_by', 'next_due_date', 'created_at')
    search_fields = (
        'customer__email',
        'customer__first_name',
        'customer__last_name',
        'notes',
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    def customer_display(self, obj):
        return obj.customer.get_full_name() or obj.customer.email
    customer_display.short_description = 'Customer'

    def credit_limit_display(self, obj):
        return f'₦ {obj.credit_limit:,.2f}'
    credit_limit_display.short_description = 'Credit Limit'

    def outstanding_balance_display(self, obj):
        return f'₦ {obj.outstanding_balance:,.2f}'
    outstanding_balance_display.short_description = 'Outstanding Balance'

    def approved_by_display(self, obj):
        if not obj.approved_by:
            return '—'
        return obj.approved_by.get_full_name() or obj.approved_by.email
    approved_by_display.short_description = 'Approved By'

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'credit_account',
        'transaction_type',
        'amount_display',
        'previous_balance_display',
        'new_balance_display',
        'sale_display',
        'payment_display',
        'created_at',
    )
    list_filter = ('transaction_type', 'created_at')
    search_fields = (
        'reference',
        'notes',
        'credit_account__customer__email',
        'credit_account__customer__first_name',
        'credit_account__customer__last_name',
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    def amount_display(self, obj):
        return f'₦ {obj.amount:,.2f}'
    amount_display.short_description = 'Amount'

    def previous_balance_display(self, obj):
        return f'₦ {obj.previous_balance:,.2f}'
    previous_balance_display.short_description = 'Previous Balance'

    def new_balance_display(self, obj):
        return f'₦ {obj.new_balance:,.2f}'
    new_balance_display.short_description = 'New Balance'

    def sale_display(self, obj):
        return obj.sale.sale_number if obj.sale else '—'
    sale_display.short_description = 'Sale'

    def payment_display(self, obj):
        return obj.payment.payment_reference if obj.payment else '—'
    payment_display.short_description = 'Payment'

    def has_delete_permission(self, request, obj=None):
        return False
