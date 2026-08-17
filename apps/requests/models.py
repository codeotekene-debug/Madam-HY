from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Request(models.Model):
    """Customer request managed independently from orders, sales, payments, credits, and inventory."""

    class RequestType(models.TextChoices):
        PRODUCT = 'PRODUCT', 'Product Request'
        GENERAL = 'GENERAL', 'General Request'
        SUPPORT = 'SUPPORT', 'Customer Support'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        REVIEWING = 'REVIEWING', 'In Review'
        APPROVED = 'APPROVED', 'Approved'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        NORMAL = 'NORMAL', 'Normal'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    request_number = models.CharField(
        max_length=80,
        unique=True,
        db_index=True,
        help_text='Unique request identifier.',
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='customer_requests',
        limit_choices_to={'role': 'CUSTOMER'},
        help_text='Customer who created the request.',
    )
    request_type = models.CharField(
        max_length=20,
        choices=RequestType.choices,
        default=RequestType.GENERAL,
        db_index=True,
        help_text='Category of the request.',
    )
    title = models.CharField(
        max_length=200,
        help_text='Short summary of the request.',
    )
    description = models.TextField(
        help_text='Detailed description of the request.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text='Current request lifecycle status.',
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
        help_text='Importance level for staff handling.',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='requests',
        help_text='Optional product relevant to this request.',
    )
    quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Requested quantity when this request concerns a product.',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_requests',
        help_text='Staff member currently assigned to review the request.',
    )
    resolution = models.TextField(
        blank=True,
        help_text='Staff response or resolution details.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the request was resolved or completed.',
    )

    class Meta:
        ordering = ['-updated_at', '-created_at']
        verbose_name = 'Request'
        verbose_name_plural = 'Requests'
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['priority', '-created_at']),
            models.Index(fields=['request_type', '-created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['assigned_to', '-created_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['request_number'], name='request_number_unique'),
            models.CheckConstraint(
                check=models.Q(quantity__isnull=True) | models.Q(quantity__gt=0),
                name='request_quantity_positive',
            ),
        ]

    def __str__(self):
        return f'{self.request_number} - {self.title}'

    def clean(self):
        super().clean()

        if not self.customer_id:
            raise ValidationError({'customer': 'Every request must belong to a CUSTOMER.'})

        if self.customer and self.customer.role != 'CUSTOMER':
            raise ValidationError({'customer': 'Only CUSTOMER role users can create requests.'})

        if self.request_type == self.RequestType.PRODUCT and not self.product:
            raise ValidationError({'product': 'Product requests should normally include a product.'})

        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be positive when supplied.'})

        if self.assigned_to and self.assigned_to.role not in {'OWNER', 'MANAGER', 'CASHIER', 'STAFF'}:
            raise ValidationError({'assigned_to': 'Assigned staff must be an authorized staff-level user.'})

        if self.assigned_to and self.assigned_to.role == 'CUSTOMER':
            raise ValidationError({'assigned_to': 'Customers cannot be assigned to requests.'})

        if self.resolved_at and self.status not in {self.Status.APPROVED, self.Status.PROCESSING, self.Status.COMPLETED, self.Status.REJECTED, self.Status.CANCELLED}:
            raise ValidationError({'resolved_at': 'Resolved timestamp is only valid for resolved or closed requests.'})

        if self.status == self.Status.COMPLETED and not self.resolution.strip():
            raise ValidationError({'resolution': 'Completed requests must include a resolution or response.'})

        if self.status in {self.Status.REJECTED, self.Status.CANCELLED} and self.resolved_at is None:
            raise ValidationError({'resolved_at': 'Rejected or cancelled requests should record when they were resolved.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.status in {self.Status.COMPLETED, self.Status.REJECTED, self.Status.CANCELLED} and self.resolved_at is None:
            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in {self.Status.COMPLETED, self.Status.REJECTED, self.Status.CANCELLED} or self.resolved_at:
            raise ValidationError('Historical request records must be preserved. They cannot be casually deleted.')
        return super().delete(*args, **kwargs)
