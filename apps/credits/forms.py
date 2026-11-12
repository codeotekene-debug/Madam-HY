from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError


PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Cash'),
    ('BANK_TRANSFER', 'Bank Transfer'),
    ('CARD', 'Card / POS'),
]


class CreditRepaymentForm(forms.Form):
    """Form for validating staff credit repayment submissions."""

    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        max_digits=14,
        required=True,
        error_messages={
            'required': 'Repayment amount is required.',
            'min_value': 'Repayment amount must be strictly greater than zero.',
            'invalid': 'Valid repayment amount is required.',
        },
    )
    payment_method = forms.CharField(
        max_length=30,
        required=True,
        error_messages={
            'required': 'Payment method is required.',
        },
    )
    reference = forms.CharField(
        max_length=120,
        required=False,
    )
    notes = forms.CharField(
        widget=forms.Textarea,
        required=False,
    )

    def __init__(self, *args, account=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = account

    def clean_payment_method(self):
        method = (self.cleaned_data.get('payment_method') or '').strip().upper()
        if not method:
            raise ValidationError('Payment method is required.')

        valid_methods = {'CASH', 'BANK_TRANSFER', 'TRANSFER', 'CARD', 'POS'}
        if method not in valid_methods:
            raise ValidationError(
                f'Invalid payment method "{method}". Accepted methods are CASH, BANK_TRANSFER, CARD (or POS/TRANSFER).'
            )

        if method == 'TRANSFER':
            return 'BANK_TRANSFER'
        if method == 'POS':
            return 'CARD'
        return method

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        if amount and self.account is not None:
            if amount > self.account.outstanding_balance:
                self.add_error(
                    'amount',
                    f'Repayment amount ({amount:.2f}) cannot exceed current outstanding balance ({self.account.outstanding_balance:.2f}).',
                )
        return cleaned_data


TRANSACTION_TYPE_CHOICES = [
    ('TOP_UP', 'Top Up / Store Credit Deposit'),
    ('CREDIT_LIMIT_ADJUSTMENT', 'Credit Limit Adjustment'),
    ('MANUAL_OVERRIDE', 'Manual Override / Balance Adjustment'),
]


class CustomerCreditProvisionForm(forms.Form):
    """Form for validating Manager/Owner credit provisioning and top-ups."""

    customer_id = forms.IntegerField(
        required=True,
        error_messages={'required': 'Customer ID is required.'},
    )
    amount = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        max_digits=14,
        required=True,
        error_messages={
            'required': 'Credit amount is required.',
            'min_value': 'Credit amount must be strictly greater than zero.',
            'invalid': 'Valid credit amount is required.',
        },
    )
    credit_limit = forms.DecimalField(
        min_value=Decimal('0.00'),
        decimal_places=2,
        max_digits=14,
        required=False,
    )
    transaction_type = forms.ChoiceField(
        choices=TRANSACTION_TYPE_CHOICES,
        required=False,
        initial='TOP_UP',
    )
    notes = forms.CharField(
        widget=forms.Textarea,
        required=True,
        error_messages={'required': 'Manager reason/note is mandatory.'},
    )

