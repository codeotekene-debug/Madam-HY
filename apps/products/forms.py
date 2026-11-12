from django import forms

from .models import Product, ProductCategory


class ProductForm(forms.ModelForm):
    """
    Product catalog definition form.
    Strictly manages product identity, pricing, and catalog attributes.
    Stock control is strictly separated and managed through apps/inventory.
    """

    class Meta:
        model = Product
        fields = [
            'name',
            'category',
            'sku',
            'selling_price',
            'cost_price',
            'reorder_level',
            'allow_pay_on_delivery',
            'description',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Silk Chiffon Fabric'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. MH-FAB-001'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'allow_pay_on_delivery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # Explicit safety check: stock_quantity must never be modified via product forms
        if 'stock_quantity' in self.cleaned_data:
            self.cleaned_data.pop('stock_quantity', None)

        selling_price = cleaned_data.get('selling_price')
        cost_price = cleaned_data.get('cost_price')

        if selling_price is not None and cost_price is not None:
            if selling_price < cost_price:
                self.add_error('selling_price', 'Selling price cannot be lower than cost price.')

        return cleaned_data


class ProductEditForm(ProductForm):
    """
    Product catalog edit form.
    Stock quantity cannot be edited directly; inventory modifications must go
    through the inventory ledger workflow (/inventory/adjust/).
    """
    pass
