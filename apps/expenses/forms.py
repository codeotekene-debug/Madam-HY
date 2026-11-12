from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Expense


class ExpenseForm(forms.Form):
    """Form for creating and validating business expense records."""

    category = forms.CharField(
        max_length=25,
        required=True,
        error_messages={'required': 'Category is required.'},
    )
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        max_digits=12,
        required=True,
        error_messages={
            'required': 'Expense amount is required.',
            'min_value': 'Expense amount must be strictly greater than zero.',
        },
    )
    expense_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    date_incurred = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Alternative field name for expense_date.',
    )
    vendor = forms.CharField(
        max_length=200,
        required=False,
    )
    payment_method = forms.CharField(
        max_length=20,
        required=False,
    )
    payment_reference = forms.CharField(
        max_length=120,
        required=False,
    )
    expense_reference = forms.CharField(
        max_length=80,
        required=False,
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    receipt_image = forms.ImageField(
        required=False,
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def clean_category(self):
        cat = (self.cleaned_data.get('category') or '').strip().upper()
        valid = {c.value for c in Expense.Category}
        if cat not in valid:
            raise ValidationError(f'Invalid category "{cat}". Valid categories are: {", ".join(sorted(valid))}.')
        return cat

    def clean_payment_method(self):
        pm = (self.cleaned_data.get('payment_method') or 'CASH').strip().upper()
        if pm == 'TRANSFER':
            pm = 'BANK_TRANSFER'
        valid = {m.value for m in Expense.PaymentMethod}
        if pm not in valid:
            raise ValidationError(f'Invalid payment method "{pm}". Valid methods are: {", ".join(sorted(valid))}.')
        return pm

    def clean(self):
        cleaned_data = super().clean()
        exp_date = cleaned_data.get('expense_date') or cleaned_data.get('date_incurred')
        if not exp_date:
            self.add_error('expense_date', 'Expense date (or date incurred) is required.')
        else:
            cleaned_data['expense_date'] = exp_date

        if not cleaned_data.get('vendor'):
            cleaned_data['vendor'] = 'General'

        return cleaned_data


class ExpenseRejectionForm(forms.Form):
    """Form for supplying an optional rejection reason."""

    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional reason for rejection'}),
    )
