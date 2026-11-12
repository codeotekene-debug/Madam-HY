from datetime import date
from decimal import Decimal, InvalidOperation
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity
from .models import Expense


class ExpenseService:
    """Centralized service for managing business expenses and approval workflows."""

    ALLOWED_CREATORS = {'OWNER', 'MANAGER', 'CASHIER', 'STAFF'}
    ALLOWED_APPROVERS = {'OWNER', 'MANAGER'}

    @classmethod
    @transaction.atomic
    def create_expense(
        cls,
        recorded_by,
        amount,
        category,
        expense_date,
        vendor=None,
        payment_method=None,
        description='',
        payment_reference='',
        expense_reference=None,
        notes='',
        receipt_image=None,
    ):
        """Create a new business expense in PENDING status."""
        if not recorded_by or getattr(recorded_by, 'role', None) not in cls.ALLOWED_CREATORS:
            raise ValidationError({'recorded_by': 'Only staff or owner roles can record expenses.'})

        if amount is None:
            raise ValidationError({'amount': 'Expense amount is required.'})
        try:
            numeric_amount = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({'amount': 'Valid monetary amount is required.'})

        if numeric_amount <= Decimal('0.00'):
            raise ValidationError({'amount': 'Expense amount must be strictly greater than zero.'})

        # Category normalization
        category_normalized = str(category or '').strip().upper()
        valid_categories = {choice.value for choice in Expense.Category}
        if category_normalized not in valid_categories:
            raise ValidationError({
                'category': f'Invalid category "{category}". Valid categories are: {", ".join(sorted(valid_categories))}.'
            })

        # Payment method normalization
        pm_normalized = str(payment_method or Expense.PaymentMethod.CASH).strip().upper()
        if pm_normalized == 'TRANSFER':
            pm_normalized = 'BANK_TRANSFER'
        valid_methods = {choice.value for choice in Expense.PaymentMethod}
        if pm_normalized not in valid_methods:
            raise ValidationError({
                'payment_method': f'Invalid payment method "{payment_method}". Valid methods: {", ".join(sorted(valid_methods))}.'
            })

        # Reference auto-generation if not supplied
        if not expense_reference or not str(expense_reference).strip():
            ref = f'EXP-{uuid.uuid4().hex[:8].upper()}'
            while Expense.objects.filter(expense_reference=ref).exists():
                ref = f'EXP-{uuid.uuid4().hex[:8].upper()}'
            expense_reference = ref
        else:
            expense_reference = str(expense_reference).strip()

        vendor_name = (vendor or '').strip() or 'General'

        expense = Expense(
            expense_reference=expense_reference,
            category=category_normalized,
            description=(description or '').strip(),
            amount=numeric_amount,
            expense_date=expense_date,
            vendor=vendor_name,
            payment_method=pm_normalized,
            payment_reference=(payment_reference or '').strip(),
            status=Expense.Status.PENDING,
            recorded_by=recorded_by,
            notes=(notes or '').strip(),
        )

        if receipt_image:
            expense.receipt_image = receipt_image

        expense.full_clean()
        expense.save()

        # Audit log creation
        log_activity(
            actor=recorded_by,
            action_type=ActivityLog.ActionType.CREATED,
            action_label='Expense recorded',
            description=(
                f'Expense {expense.expense_reference} of {expense.amount:.2f} '
                f'({expense.get_category_display()}) recorded by {recorded_by.email}.'
            ),
            related_object=expense,
            metadata={
                'expense_id': expense.pk,
                'expense_uuid': str(expense.uuid),
                'expense_reference': expense.expense_reference,
                'amount': str(expense.amount),
                'category': expense.category,
                'status': expense.status,
                'vendor': expense.vendor,
            },
        )

        return expense

    @classmethod
    @transaction.atomic
    def approve_expense(cls, expense, approved_by):
        """Approve a pending business expense."""
        if not approved_by or getattr(approved_by, 'role', None) not in cls.ALLOWED_APPROVERS:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can approve expenses.'})

        if expense is None:
            raise ValidationError({'expense': 'Expense record is required.'})

        # Lock expense row
        locked_expense = Expense.objects.select_for_update().get(pk=expense.pk)

        if locked_expense.status == Expense.Status.APPROVED:
            raise ValidationError({'status': 'Expense is already approved.'})
        if locked_expense.status == Expense.Status.REJECTED:
            raise ValidationError({'status': 'Rejected expenses cannot be approved.'})

        locked_expense.approve(approved_by)

        log_activity(
            actor=approved_by,
            action_type=ActivityLog.ActionType.APPROVED,
            action_label='Expense approved',
            description=(
                f'Expense {locked_expense.expense_reference} ({locked_expense.amount:.2f}) '
                f'approved by {approved_by.email}.'
            ),
            related_object=locked_expense,
            metadata={
                'expense_id': locked_expense.pk,
                'expense_uuid': str(locked_expense.uuid),
                'expense_reference': locked_expense.expense_reference,
                'amount': str(locked_expense.amount),
                'approved_by': approved_by.email,
            },
        )

        return locked_expense

    @classmethod
    @transaction.atomic
    def reject_expense(cls, expense, rejected_by, reason=''):
        """Reject a pending business expense."""
        if not rejected_by or getattr(rejected_by, 'role', None) not in cls.ALLOWED_APPROVERS:
            raise ValidationError({'approved_by': 'Only OWNER or MANAGER can reject expenses.'})

        if expense is None:
            raise ValidationError({'expense': 'Expense record is required.'})

        # Lock expense row
        locked_expense = Expense.objects.select_for_update().get(pk=expense.pk)

        if locked_expense.status == Expense.Status.APPROVED:
            raise ValidationError({'status': 'Approved expenses cannot be rejected.'})
        if locked_expense.status == Expense.Status.REJECTED:
            raise ValidationError({'status': 'Expense is already rejected.'})

        locked_expense.reject(rejected_by, reason=reason)

        log_activity(
            actor=rejected_by,
            action_type=ActivityLog.ActionType.REJECTED,
            action_label='Expense rejected',
            description=(
                f'Expense {locked_expense.expense_reference} ({locked_expense.amount:.2f}) '
                f'rejected by {rejected_by.email}. Reason: {reason or "N/A"}'
            ),
            related_object=locked_expense,
            metadata={
                'expense_id': locked_expense.pk,
                'expense_uuid': str(locked_expense.uuid),
                'expense_reference': locked_expense.expense_reference,
                'amount': str(locked_expense.amount),
                'rejected_by': rejected_by.email,
                'reason': reason or '',
            },
        )

        return locked_expense

    @classmethod
    def get_expense_summary(cls, queryset):
        """Aggregate summary metrics for an expenses queryset."""
        total_expenses = queryset.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        approved_total = queryset.filter(status=Expense.Status.APPROVED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        pending_count = queryset.filter(status=Expense.Status.PENDING).count()

        today = date.today()
        month_expenses = queryset.filter(
            expense_date__year=today.year,
            expense_date__month=today.month,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        year_expenses = queryset.filter(
            expense_date__year=today.year,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        top_cat_row = (
            queryset.values('category')
            .annotate(cat_total=Sum('amount'))
            .order_by('-cat_total')
            .first()
        )
        top_category = top_cat_row['category'] if top_cat_row else '-'

        return {
            'total_expenses': str(total_expenses),
            'approved_total': str(approved_total),
            'pending_count': pending_count,
            'month_expenses': str(month_expenses),
            'year_expenses': str(year_expenses),
            'top_category': top_category,
        }
