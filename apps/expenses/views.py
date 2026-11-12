from datetime import date
from decimal import Decimal
import json
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import role_required
from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity

from .forms import ExpenseForm, ExpenseRejectionForm
from .models import Expense
from .services import ExpenseService

User = get_user_model()
ALL_EXPENSE_MANAGERS = ('OWNER', 'MANAGER')
ALL_EXPENSE_STAFF = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')


def _json_response(data=None, message='Success', success=True, status=200, errors=None):
    payload = {'success': success, 'message': message}
    if data is not None:
        payload['data'] = data
    if errors is not None:
        payload['errors'] = errors
    response = JsonResponse(payload, status=status)
    if data is not None and isinstance(data, dict):
        response.context = {**payload, **data}
    elif data is not None:
        response.context = payload
    return response


def _is_authenticated(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def _wants_json(request):
    format_param = (request.GET.get('format') or '').lower()
    if format_param == 'json':
        return True
    if format_param == 'html':
        return False
    content_type = request.content_type or request.headers.get('content-type', '')
    if 'application/json' in content_type:
        return True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('accept', '')
    if 'text/html' in accept and 'application/json' not in accept:
        return False
    return True


def _serialize_user(user):
    if user is None:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name(),
        'role': user.role,
    }


def _serialize_expense(expense):
    if expense is None:
        return None
    return {
        'id': expense.id,
        'uuid': str(expense.uuid),
        'expense_reference': expense.expense_reference,
        'category': expense.category,
        'category_display': expense.get_category_display(),
        'description': expense.description,
        'amount': str(expense.amount),
        'expense_date': expense.expense_date.isoformat() if expense.expense_date else None,
        'vendor': expense.vendor,
        'payment_method': expense.payment_method,
        'payment_method_display': expense.get_payment_method_display(),
        'payment_reference': expense.payment_reference,
        'status': expense.status,
        'status_display': expense.get_status_display(),
        'recorded_by': _serialize_user(expense.recorded_by),
        'approved_by': _serialize_user(expense.approved_by),
        'approved_at': expense.approved_at.isoformat() if expense.approved_at else None,
        'rejection_reason': expense.rejection_reason,
        'receipt_image_url': expense.receipt_image.url if expense.receipt_image else None,
        'notes': expense.notes,
        'created_at': expense.created_at.isoformat() if expense.created_at else None,
        'updated_at': expense.updated_at.isoformat() if expense.updated_at else None,
    }


def _get_expense(expense_id):
    """Retrieve an expense by UUID, integer PK, or expense reference."""
    if not expense_id:
        return None
    expense_id_str = str(expense_id).strip()

    # Try UUID lookup
    try:
        val = uuid.UUID(expense_id_str)
        return Expense.objects.select_related('recorded_by', 'approved_by').get(uuid=val)
    except (ValueError, TypeError, Expense.DoesNotExist):
        pass

    # Try integer PK lookup
    try:
        pk = int(expense_id_str)
        return Expense.objects.select_related('recorded_by', 'approved_by').get(pk=pk)
    except (ValueError, TypeError, Expense.DoesNotExist):
        pass

    # Try expense_reference lookup
    try:
        return Expense.objects.select_related('recorded_by', 'approved_by').get(expense_reference__iexact=expense_id_str)
    except Expense.DoesNotExist:
        pass

    return None


def _parse_request_payload(request):
    """Parse JSON body if present, or fallback to request.POST."""
    if request.body:
        content_type = request.content_type or request.headers.get('content-type', '')
        if 'application/json' in content_type:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
                if isinstance(payload, dict):
                    return payload, None
                return None, {'body': 'Request body must be a JSON object.'}
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return None, {'body': 'Invalid JSON in request body.'}
    if request.POST:
        return request.POST.dict(), None
    if request.body:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            if isinstance(payload, dict):
                return payload, None
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            pass
    return {}, None


# ==============================================================================
# Views
# ==============================================================================


def expense_list(request):
    """
    Paginated expense list supporting date range, category, status, and search filters.
    Staff/Cashiers can only view their own incurred expenses; Owners/Managers view all.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect('accounts:login')

    user_role = getattr(request.user, 'role', None)
    if user_role == 'CUSTOMER':
        return _json_response(message='Customers are not authorized to view expenses.', success=False, status=403)
    if user_role not in ALL_EXPENSE_STAFF:
        return _json_response(message='Permission denied.', success=False, status=403)

    # Scoping: Staff & Cashier only see their own recorded expenses
    if user_role in ('CASHIER', 'STAFF'):
        qs = Expense.objects.filter(recorded_by=request.user)
    else:
        qs = Expense.objects.all()

    qs = qs.select_related('recorded_by', 'approved_by')

    # Date range filters
    start_date = (request.GET.get('start_date') or '').strip()
    if start_date:
        qs = qs.filter(expense_date__gte=start_date)

    end_date = (request.GET.get('end_date') or '').strip()
    if end_date:
        qs = qs.filter(expense_date__lte=end_date)

    # Category filter
    category = (request.GET.get('category') or '').strip().upper()
    if category and category != 'ALL':
        qs = qs.filter(category=category)

    # Status filter (PENDING, APPROVED, REJECTED)
    status_filter = (request.GET.get('status') or '').strip().upper()
    if status_filter and status_filter != 'ALL':
        qs = qs.filter(status=status_filter)

    # Search filter (description, vendor, reference, notes)
    search_query = (request.GET.get('search') or '').strip()
    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query)
            | Q(vendor__icontains=search_query)
            | Q(expense_reference__icontains=search_query)
            | Q(payment_reference__icontains=search_query)
            | Q(notes__icontains=search_query)
        )

    # Summary metrics
    summary = ExpenseService.get_expense_summary(qs)

    # Pagination
    try:
        page_size = min(100, max(1, int(request.GET.get('page_size', 10))))
        page_number = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page_size = 10
        page_number = 1

    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    serialized_expenses = [_serialize_expense(exp) for exp in page_obj.object_list]

    data = {
        'summary': summary,
        'expenses': serialized_expenses,
        'pagination': {
            'page': page_obj.number,
            'pages': paginator.num_pages,
            'total_count': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    }

    if _wants_json(request):
        return _json_response(data=data, message='Expenses retrieved successfully.')

    return render(
        request,
        'expenses/expenses.html',
        {
            'expenses': page_obj.object_list,
            'page_obj': page_obj,
            'summary': summary,
            'search_query': search_query,
            'category_filter': category,
            'status_filter': status_filter,
            'start_date': start_date,
            'end_date': end_date,
            'active_module': 'expenses',
            'active_tab': 'list',
        },
    )


def expense_create(request):
    """
    Record a new expense.
    Staff and Cashiers can record expenses; Owners and Managers can also record.
    """
    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect('accounts:login')

    user_role = getattr(request.user, 'role', None)
    if user_role == 'CUSTOMER':
        return _json_response(message='Customers are not authorized to record expenses.', success=False, status=403)
    if user_role not in ALL_EXPENSE_STAFF:
        return _json_response(message='Permission denied.', success=False, status=403)

    if request.method == 'GET':
        if _wants_json(request):
            return _json_response(message='Use POST to create an expense.', success=False, status=405)
        return render(
            request,
            'expenses/add_expense.html',
            {
                'active_module': 'expenses',
                'active_tab': 'create',
            },
        )

    if request.method != 'POST':
        return _json_response(message='Only POST is allowed.', success=False, status=405)

    payload, parse_err = _parse_request_payload(request)
    if parse_err:
        return _json_response(message='Validation failed.', success=False, status=400, errors=parse_err)

    form = ExpenseForm(data=payload, files=request.FILES)
    if not form.is_valid():
        errors = {field: [str(err) for err in errs] for field, errs in form.errors.items()}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    try:
        expense = ExpenseService.create_expense(
            recorded_by=request.user,
            amount=form.cleaned_data['amount'],
            category=form.cleaned_data['category'],
            expense_date=form.cleaned_data['expense_date'],
            vendor=form.cleaned_data.get('vendor'),
            payment_method=form.cleaned_data.get('payment_method'),
            description=form.cleaned_data.get('description', ''),
            payment_reference=form.cleaned_data.get('payment_reference', ''),
            expense_reference=form.cleaned_data.get('expense_reference'),
            notes=form.cleaned_data.get('notes', ''),
            receipt_image=form.cleaned_data.get('receipt_image'),
        )
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    serialized = _serialize_expense(expense)

    if _wants_json(request):
        return _json_response(
            data=serialized,
            message='Expense recorded successfully.',
            success=True,
            status=201,
        )

    return redirect('expenses:expense_detail', id=expense.uuid)


def expense_detail(request, id):
    """
    Detailed view of an expense including audit stamps and receipt attachment.
    Staff/Cashiers can only view expenses they recorded; Owners/Managers view any.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect('accounts:login')

    user_role = getattr(request.user, 'role', None)
    if user_role == 'CUSTOMER':
        return _json_response(message='Customers are not authorized to view expenses.', success=False, status=403)
    if user_role not in ALL_EXPENSE_STAFF:
        return _json_response(message='Permission denied.', success=False, status=403)

    expense = _get_expense(id)
    if expense is None:
        return _json_response(message='Expense not found.', success=False, status=404)

    # Scoping check: Staff/Cashier can only view their own expenses
    if user_role in ('CASHIER', 'STAFF') and expense.recorded_by_id != request.user.id:
        return _json_response(
            message='You do not have permission to view this expense.',
            success=False,
            status=403,
        )

    # Audit logging for viewing detail
    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Viewed expense detail',
        description=f'User {request.user.email} viewed expense {expense.expense_reference}.',
        related_object=expense,
        metadata={
            'expense_id': expense.pk,
            'expense_uuid': str(expense.uuid),
            'expense_reference': expense.expense_reference,
        },
    )

    serialized = _serialize_expense(expense)

    if _wants_json(request):
        return _json_response(data=serialized, message='Expense details retrieved successfully.')

    return render(
        request,
        'expenses/expense_detail.html',
        {
            'expense': expense,
            'serialized': serialized,
            'active_module': 'expenses',
            'active_tab': 'list',
        },
    )


def expense_approve(request, id):
    """
    Approve a pending business expense.
    Restricted strictly to OWNER and MANAGER roles.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed for approvals.', success=False, status=405)

    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    user_role = getattr(request.user, 'role', None)
    if user_role not in ALL_EXPENSE_MANAGERS:
        return _json_response(
            message='Only OWNER or MANAGER can approve expenses.',
            success=False,
            status=403,
        )

    expense = _get_expense(id)
    if expense is None:
        return _json_response(message='Expense not found.', success=False, status=404)

    try:
        updated_expense = ExpenseService.approve_expense(expense=expense, approved_by=request.user)
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    serialized = _serialize_expense(updated_expense)
    return _json_response(
        data=serialized,
        message=f'Expense {updated_expense.expense_reference} approved successfully.',
        success=True,
        status=200,
    )


def expense_reject(request, id):
    """
    Reject a pending business expense.
    Restricted strictly to OWNER and MANAGER roles.
    """
    if request.method != 'POST':
        return _json_response(message='Only POST is allowed for rejections.', success=False, status=405)

    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    user_role = getattr(request.user, 'role', None)
    if user_role not in ALL_EXPENSE_MANAGERS:
        return _json_response(
            message='Only OWNER or MANAGER can reject expenses.',
            success=False,
            status=403,
        )

    expense = _get_expense(id)
    if expense is None:
        return _json_response(message='Expense not found.', success=False, status=404)

    payload, _ = _parse_request_payload(request)
    form = ExpenseRejectionForm(payload)
    reason = form.cleaned_data.get('reason', '') if form.is_valid() else payload.get('reason', '')

    try:
        updated_expense = ExpenseService.reject_expense(
            expense=expense,
            rejected_by=request.user,
            reason=reason,
        )
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    serialized = _serialize_expense(updated_expense)
    return _json_response(
        data=serialized,
        message=f'Expense {updated_expense.expense_reference} rejected successfully.',
        success=True,
        status=200,
    )


@role_required('OWNER', 'MANAGER')
def expense_categories_view(request):
    """
    List expense category breakdowns and analytics.
    Strictly restricted to OWNER and MANAGER roles.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    all_expenses = Expense.objects.all()
    total_amount = sum(e.amount for e in all_expenses)

    categories_data = []
    for cat_value, cat_label in Expense.Category.choices:
        cat_expenses = all_expenses.filter(category=cat_value)
        count = cat_expenses.count()
        spent = sum(e.amount for e in cat_expenses)
        pct = (
            round((float(spent) / float(total_amount) * 100), 1)
            if total_amount > 0
            else 0.0
        )
        categories_data.append({
            'category': cat_value,
            'label': cat_label,
            'count': count,
            'total_spent': str(spent),
            'percentage': pct,
        })

    data = {
        'total_categories': len(Expense.Category.choices),
        'total_amount': str(total_amount),
        'categories': categories_data,
    }

    if _wants_json(request):
        return _json_response(data=data, message='Expense categories retrieved.')

    return render(
        request,
        'expenses/categories.html',
        {
            'categories': categories_data,
            'total_amount': total_amount,
            'active_module': 'expenses',
            'active_tab': 'categories',
        },
    )


@role_required('OWNER', 'MANAGER')
def expense_summary_view(request):
    """
    Comprehensive business expense summary and analytics dashboard.
    Strictly restricted to OWNER and MANAGER roles.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    qs = Expense.objects.all()
    summary = ExpenseService.get_expense_summary(qs)

    today = date.today()
    this_month_qs = qs.filter(expense_date__year=today.year, expense_date__month=today.month)
    this_month_total = sum(e.amount for e in this_month_qs)

    approved_qs = qs.filter(status=Expense.Status.APPROVED)
    pending_qs = qs.filter(status=Expense.Status.PENDING)
    rejected_qs = qs.filter(status=Expense.Status.REJECTED)

    # Payment method breakdown
    payment_methods = {}
    for exp in qs:
        pm = exp.get_payment_method_display() or exp.payment_method
        payment_methods[pm] = payment_methods.get(pm, Decimal('0.00')) + exp.amount

    by_category = {}
    for exp in qs:
        cat = exp.get_category_display() or exp.category
        by_category[cat] = by_category.get(cat, Decimal('0.00')) + exp.amount

    summary_data = {
        'total_expenses': str(summary.get('total_expenses', '0.00')),
        'total_count': qs.count(),
        'pending_approval': str(sum(e.amount for e in pending_qs)),
        'pending_count': pending_qs.count(),
        'approved_total': str(sum(e.amount for e in approved_qs)),
        'approved_count': approved_qs.count(),
        'rejected_count': rejected_qs.count(),
        'this_month_total': str(this_month_total),
        'this_month_count': this_month_qs.count(),
        'by_category': {k: str(v) for k, v in by_category.items()},
        'payment_methods': {k: str(v) for k, v in payment_methods.items()},
    }

    if _wants_json(request):
        return _json_response(data=summary_data, message='Expense summary retrieved.')

    return render(
        request,
        'expenses/expense_summary.html',
        {
            'summary': summary_data,
            'recent_expenses': qs.select_related('recorded_by', 'approved_by')[:20],
            'active_module': 'expenses',
            'active_tab': 'summary',
        },
    )
