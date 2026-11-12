from django import forms
from django.contrib.auth import get_user_model

from apps.products.models import Product
from .models import Request

User = get_user_model()
STAFF_MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


class CustomerRequestCreateForm(forms.ModelForm):
    """Form used by customers to submit tickets and inquiries."""

    class Meta:
        model = Request
        fields = [
            'request_type',
            'priority',
            'title',
            'description',
            'product',
            'quantity',
            'notes',
            'attachment',
        ]
        widgets = {
            'request_type': forms.Select(attrs={'class': 'form-select', 'id': 'requestType'}),
            'priority': forms.Select(attrs={'class': 'form-select', 'id': 'requestPriority'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'id': 'requestTitle', 'placeholder': 'Briefly describe your request'}),
            'description': forms.Textarea(attrs={'class': 'form-control textarea-control', 'id': 'requestDescription', 'rows': 5, 'placeholder': 'Describe the issue or inquiry in detail'}),
            'product': forms.Select(attrs={'class': 'form-select', 'id': 'requestProduct'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'id': 'requestQuantity', 'min': 1, 'placeholder': 'e.g. 5'}),
            'notes': forms.Textarea(attrs={'class': 'form-control textarea-control', 'id': 'requestNotes', 'rows': 3, 'placeholder': 'Optional extra context or delivery instructions'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control', 'id': 'requestAttachment'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = True
        self.fields['description'].required = True
        self.fields['product'].required = False
        self.fields['quantity'].required = False
        self.fields['notes'].required = False
        self.fields['attachment'].required = False

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise forms.ValidationError('Title is required.')
        return title

    def clean_description(self):
        desc = self.cleaned_data.get('description', '').strip()
        if not desc:
            raise forms.ValidationError('Description is required.')
        return desc

    def clean(self):
        cleaned_data = super().clean()
        req_type = cleaned_data.get('request_type')
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if req_type == Request.RequestType.PRODUCT and not product:
            self.add_error('product', 'Product requests should normally include a product.')

        if quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be positive when supplied.')

        return cleaned_data


class StaffRequestCreateForm(CustomerRequestCreateForm):
    """Form used by staff to create requests on behalf of customers or internal operations."""

    customer = forms.ModelChoiceField(
        queryset=User.objects.filter(role='CUSTOMER', is_active=True),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'requestCustomer'}),
        required=True,
        empty_label='Select customer',
    )
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=STAFF_MANAGEMENT_ROLES, is_active=True),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'requestAssignee'}),
        required=False,
        empty_label='Unassigned',
    )

    class Meta(CustomerRequestCreateForm.Meta):
        fields = [
            'customer',
            'request_type',
            'priority',
            'title',
            'description',
            'product',
            'quantity',
            'assigned_to',
            'notes',
            'attachment',
        ]


class RequestStatusUpdateForm(forms.Form):
    """Form used by staff to transition ticket lifecycle status."""

    status = forms.ChoiceField(
        choices=Request.Status.choices,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'updateStatus'}),
        required=True,
    )
    resolution = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'id': 'updateResolution', 'rows': 4, 'placeholder': 'Enter resolution or staff response'}),
        required=False,
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'id': 'updateNotes', 'rows': 3, 'placeholder': 'Optional internal notes'}),
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        resolution = (cleaned_data.get('resolution') or '').strip()

        if status == Request.Status.COMPLETED and not resolution:
            self.add_error('resolution', 'Completed requests must include a resolution or response.')

        return cleaned_data


class RequestAssignForm(forms.Form):
    """Form used by management to assign or reassign tickets."""

    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=STAFF_MANAGEMENT_ROLES, is_active=True),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'assignStaff'}),
        required=False,
        empty_label='Unassigned',
    )
