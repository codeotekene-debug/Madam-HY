from datetime import date
from decimal import Decimal, InvalidOperation
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.activity_logs.models import ActivityLog
from apps.activity_logs.services import log_activity

from .forms import CreditRepaymentForm, CustomerCreditProvisionForm, TRANSACTION_TYPE_CHOICES
from .models import CreditAccount, CreditTransaction
from .services import CreditService

User = get_user_model()
MANAGEMENT_ROLES = ('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
REPAYMENT_ALLOWED_ROLES = ('OWNER', 'MANAGER', 'CASHIER')


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
        'phone_number': getattr(user, 'phone_number', ''),
        'role': user.role,
    }


def _serialize_credit_account(account):
    if account is None:
        return None
    return {
        'id': account.id,
        'customer': _serialize_user(account.customer),
        'credit_limit': str(account.credit_limit),
        'outstanding_balance': str(account.outstanding_balance),
        'available_credit': str(account.get_available_credit()),
        'status': account.status,
        'status_display': account.get_status_display(),
        'is_overdue': account.is_overdue(),
        'approved_by': _serialize_user(account.approved_by),
        'approved_at': account.approved_at.isoformat() if account.approved_at else None,
        'next_due_date': account.next_due_date.isoformat() if account.next_due_date else None,
        'last_payment_date': account.last_payment_date.isoformat() if account.last_payment_date else None,
        'notes': account.notes,
        'created_at': account.created_at.isoformat() if hasattr(account, 'created_at') and account.created_at else None,
        'updated_at': account.updated_at.isoformat() if hasattr(account, 'updated_at') and account.updated_at else None,
    }


def _serialize_credit_transaction(tx):
    if tx is None:
        return None
    return {
        'id': tx.id,
        'transaction_type': tx.transaction_type,
        'transaction_type_display': tx.get_transaction_type_display(),
        'amount': str(tx.amount),
        'previous_balance': str(tx.previous_balance),
        'new_balance': str(tx.new_balance),
        'reference': tx.reference,
        'notes': tx.notes,
        'sale_id': tx.sale_id,
        'payment_id': tx.payment_id,
        'created_by': _serialize_user(tx.created_by),
        'created_at': tx.created_at.isoformat() if tx.created_at else None,
    }


def _get_credit_account(account_id):
    """Retrieve CreditAccount by integer PK, customer ID, or username."""
    if not account_id:
        return None
    account_id_str = str(account_id).strip()

    # Try by CreditAccount PK
    try:
        pk = int(account_id_str)
        return (
            CreditAccount.objects.select_related('customer', 'approved_by')
            .prefetch_related('transactions')
            .get(pk=pk)
        )
    except (ValueError, TypeError, CreditAccount.DoesNotExist):
        pass

    # Try by Customer user PK
    try:
        return (
            CreditAccount.objects.select_related('customer', 'approved_by')
            .prefetch_related('transactions')
            .get(customer__id=int(account_id_str))
        )
    except (ValueError, TypeError, CreditAccount.DoesNotExist):
        pass

    # Try by Customer username
    try:
        return (
            CreditAccount.objects.select_related('customer', 'approved_by')
            .prefetch_related('transactions')
            .get(customer__username=account_id_str)
        )
    except CreditAccount.DoesNotExist:
        pass

    return None


def _parse_request_payload(request):
    """Parse JSON body if present, or fallback to request.POST form data."""
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


def credit_account_list(request):
    """
    List credit accounts with filtering and summary metrics.
    Staff roles can view all accounts; customers can only view their own account.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect('accounts:login')

    user_role = getattr(request.user, 'role', None)
    if user_role not in (*MANAGEMENT_ROLES, 'CUSTOMER'):
        return _json_response(message='Permission denied.', success=False, status=403)

    qs = CreditAccount.objects.select_related('customer', 'approved_by').order_by('-created_at')

    # Customer isolation
    if user_role == 'CUSTOMER':
        qs = qs.filter(customer=request.user)

    # Search filter (customer name, email, phone, username)
    search_query = (request.GET.get('search') or '').strip()
    if search_query:
        qs = qs.filter(
            Q(customer__first_name__icontains=search_query)
            | Q(customer__last_name__icontains=search_query)
            | Q(customer__email__icontains=search_query)
            | Q(customer__phone_number__icontains=search_query)
            | Q(customer__username__icontains=search_query)
        )

    # Status filter
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter and status_filter.lower() != 'all':
        status_map = {
            'active': CreditAccount.Status.ACTIVE,
            'paid': CreditAccount.Status.APPROVED,
            'approved': CreditAccount.Status.APPROVED,
            'partially paid': CreditAccount.Status.PARTIALLY_PAID,
            'partially_paid': CreditAccount.Status.PARTIALLY_PAID,
            'due': CreditAccount.Status.DUE,
            'overdue': CreditAccount.Status.OVERDUE,
            'suspended': CreditAccount.Status.SUSPENDED,
            'closed': CreditAccount.Status.CLOSED,
            'pending': CreditAccount.Status.PENDING_APPROVAL,
            'pending_approval': CreditAccount.Status.PENDING_APPROVAL,
            'rejected': CreditAccount.Status.REJECTED,
        }
        mapped_status = status_map.get(status_filter.lower(), status_filter.upper())
        qs = qs.filter(status=mapped_status)

    # Has balance filter
    has_balance = (request.GET.get('has_balance') or '').strip().lower()
    if has_balance in ('true', '1', 'yes'):
        qs = qs.filter(outstanding_balance__gt=0)
    elif has_balance in ('false', '0', 'no'):
        qs = qs.filter(outstanding_balance=0)

    # Compute summary aggregates
    total_issued = sum(acc.credit_limit for acc in qs)
    total_outstanding = sum(acc.outstanding_balance for acc in qs)
    today = date.today()
    total_overdue = sum(
        acc.outstanding_balance
        for acc in qs
        if acc.outstanding_balance > 0 and acc.next_due_date and acc.next_due_date < today
    )

    data = {
        'summary': {
            'total_issued': str(total_issued),
            'total_outstanding': str(total_outstanding),
            'total_overdue': str(total_overdue),
            'total_accounts': qs.count(),
        },
        'accounts': [_serialize_credit_account(acc) for acc in qs],
    }

    if _wants_json(request):
        return _json_response(data=data, message='Credit accounts retrieved.')

    return render(
        request,
        'credits/credits.html',
        {
            'accounts': qs,
            'accounts_serialized': data['accounts'],
            'accounts_json': json.dumps(data['accounts']),
            'summary': data['summary'],
            'search_query': search_query,
            'status_filter': status_filter,
            'has_balance': has_balance,
            'active_module': 'credits',
            'active_tab': 'accounts',
        },
    )


def credit_account_detail(request, account_id):
    """
    Detailed credit account view with limit, balance, and transaction history.
    Enforces customer isolation (customers can only view their own account).
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    if not _is_authenticated(request.user):
        if _wants_json(request):
            return _json_response(message='Authentication required.', success=False, status=401)
        return redirect('accounts:login')

    account = _get_credit_account(account_id)
    if account is None:
        return _json_response(message='Credit account not found.', success=False, status=404)

    # Customer isolation
    if request.user.role == 'CUSTOMER' and account.customer_id != request.user.id:
        return _json_response(
            message='Access denied. You can only view your own credit account.',
            success=False,
            status=403,
        )

    user_role = getattr(request.user, 'role', None)
    if user_role not in (*MANAGEMENT_ROLES, 'CUSTOMER'):
        return _json_response(message='Permission denied.', success=False, status=403)

    transactions = (
        account.transactions.select_related('created_by', 'sale', 'payment')
        .order_by('-created_at')[:50]
    )

    serialized_account = _serialize_credit_account(account)
    serialized_txs = [_serialize_credit_transaction(tx) for tx in transactions]

    # Audit log entry for viewing detail
    log_activity(
        actor=request.user,
        action_type=ActivityLog.ActionType.VIEWED,
        action_label='Viewed credit account detail',
        description=f'User {request.user.email} viewed credit account for customer {account.customer.email}.',
        related_object=account,
        metadata={
            'credit_account_id': account.pk,
            'customer_id': account.customer_id,
        },
    )

    data = {
        'account': serialized_account,
        'transactions': serialized_txs,
    }

    if _wants_json(request):
        return _json_response(data=data, message='Credit account details retrieved.')

    return render(
        request,
        'credits/credit_detail.html',
        {
            'account': account,
            'serialized_account': serialized_account,
            'serialized_account_json': json.dumps(serialized_account),
            'transactions': transactions,
            'transactions_json': json.dumps(serialized_txs),
            'active_module': 'credits',
            'active_tab': 'accounts',
        },
    )


def credit_repay(request, account_id):
    """
    Record a customer credit repayment against an account.
    Restricted to authorized staff (OWNER, MANAGER, CASHIER).
    Customers cannot record repayments directly.
    """
    if request.method != 'POST':
        if request.method == 'GET':
            return credit_payment_page(request, account_id=account_id)
        return _json_response(message='Only POST is allowed for repayments.', success=False, status=405)

    if not _is_authenticated(request.user):
        return _json_response(message='Authentication required.', success=False, status=401)

    # Role enforcement
    user_role = getattr(request.user, 'role', None)
    if user_role == 'CUSTOMER':
        return _json_response(
            message='Customers are not authorized to record credit repayments directly.',
            success=False,
            status=403,
        )
    if user_role not in REPAYMENT_ALLOWED_ROLES:
        return _json_response(
            message='Only authorized staff (OWNER, MANAGER, CASHIER) can record repayments.',
            success=False,
            status=403,
        )

    account = _get_credit_account(account_id)
    if account is None:
        return _json_response(message='Credit account not found.', success=False, status=404)

    payload, parse_err = _parse_request_payload(request)
    if parse_err:
        return _json_response(message='Validation failed.', success=False, status=400, errors=parse_err)

    form = CreditRepaymentForm(payload, account=account)
    if not form.is_valid():
        errors = {field: [str(err) for err in errs] for field, errs in form.errors.items()}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    amount = form.cleaned_data['amount']
    payment_method = form.cleaned_data['payment_method']
    reference = form.cleaned_data.get('reference', '')
    notes = form.cleaned_data.get('notes', '')

    try:
        tx, updated_account = CreditService.process_repayment(
            credit_account=account,
            amount=amount,
            payment_method=payment_method,
            created_by=request.user,
            reference=reference,
            notes=notes,
        )
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
        return _json_response(message='Validation failed.', success=False, status=400, errors=errors)

    data = {
        'account': _serialize_credit_account(updated_account),
        'transaction': _serialize_credit_transaction(tx),
    }

    return _json_response(
        data=data,
        message=f'Repayment of {tx.amount} recorded successfully.',
        success=True,
        status=200,
    )


@role_required('OWNER', 'MANAGER', 'CASHIER')
def credit_payment_page(request, account_id=None):
    """
    Renders the credit payment form page for staff.
    """
    account = None
    if account_id:
        account = _get_credit_account(account_id)

    # Available accounts with balance for select dropdown
    accounts_with_balance = CreditAccount.objects.filter(outstanding_balance__gt=0).select_related('customer')

    return render(
        request,
        'credits/credit_payment.html',
        {
            'selected_account': account,
            'accounts_with_balance': accounts_with_balance,
            'active_module': 'credits',
            'active_tab': 'settle',
        },
    )


def credit_detail_page(request, account_id=None):
    """
    Renders the credit detail template for viewing in browser.
    """
    if account_id:
        return credit_account_detail(request, account_id)
    return redirect('credits:credit_account_list')


@role_required('OWNER', 'MANAGER', 'CASHIER', 'STAFF')
def credit_transactions_view(request):
    """
    List credit transaction ledger with filtering by transaction type and search.
    Staff roles can view transactions; customers are isolated/forbidden.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    qs = CreditTransaction.objects.select_related(
        'credit_account__customer',
        'created_by',
        'sale',
        'payment',
    ).order_by('-created_at')

    # Type filter
    tx_type = (request.GET.get('type') or '').strip().upper()
    if tx_type and tx_type != 'ALL':
        qs = qs.filter(transaction_type=tx_type)

    # Search filter
    search_query = (request.GET.get('search') or '').strip()
    if search_query:
        qs = qs.filter(
            Q(reference__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(credit_account__customer__first_name__icontains=search_query)
            | Q(credit_account__customer__last_name__icontains=search_query)
            | Q(credit_account__customer__username__icontains=search_query)
        )

    serialized_txs = [_serialize_credit_transaction(tx) for tx in qs[:100]]

    data = {
        'total_count': qs.count(),
        'transactions': serialized_txs,
    }

    if _wants_json(request):
        return _json_response(data=data, message='Credit transactions retrieved.')

    return render(
        request,
        'credits/credit_transactions.html',
        {
            'transactions': qs[:100],
            'search_query': search_query,
            'type_filter': tx_type,
            'active_module': 'credits',
            'active_tab': 'transactions',
        },
    )


@role_required('OWNER', 'MANAGER')
def credit_report_view(request):
    """
    Credit Aging and Portfolio Limits Report.
    Strictly restricted to OWNER and MANAGER roles.
    """
    if request.method != 'GET':
        return _json_response(message='Only GET is allowed.', success=False, status=405)

    today = date.today()
    accounts = CreditAccount.objects.select_related('customer').all()

    total_credit_limit = sum(acc.credit_limit for acc in accounts)
    total_outstanding = sum(acc.outstanding_balance for acc in accounts)
    accounts_with_balance = [acc for acc in accounts if acc.outstanding_balance > 0]

    current_bucket = []
    days_1_30 = []
    days_31_60 = []
    days_60_plus = []

    for acc in accounts_with_balance:
        if not acc.next_due_date or acc.next_due_date >= today:
            current_bucket.append(acc)
        else:
            days_overdue = (today - acc.next_due_date).days
            if days_overdue <= 30:
                days_1_30.append(acc)
            elif days_overdue <= 60:
                days_31_60.append(acc)
            else:
                days_60_plus.append(acc)

    total_current = sum(acc.outstanding_balance for acc in current_bucket)
    total_1_30 = sum(acc.outstanding_balance for acc in days_1_30)
    total_31_60 = sum(acc.outstanding_balance for acc in days_31_60)
    total_60_plus = sum(acc.outstanding_balance for acc in days_60_plus)
    total_overdue = total_1_30 + total_31_60 + total_60_plus

    utilization_rate = (
        round((float(total_outstanding) / float(total_credit_limit) * 100), 1)
        if total_credit_limit > 0
        else 0.0
    )

    aging_summary = {
        'total_accounts': accounts.count(),
        'accounts_with_balance': len(accounts_with_balance),
        'total_credit_limit': str(total_credit_limit),
        'total_outstanding': str(total_outstanding),
        'total_overdue': str(total_overdue),
        'utilization_rate': utilization_rate,
        'current': {'count': len(current_bucket), 'amount': str(total_current)},
        'days_1_30': {'count': len(days_1_30), 'amount': str(total_1_30)},
        'days_31_60': {'count': len(days_31_60), 'amount': str(total_31_60)},
        'days_60_plus': {'count': len(days_60_plus), 'amount': str(total_60_plus)},
    }

    if _wants_json(request):
        return _json_response(data=aging_summary, message='Credit aging report retrieved.')

    return render(
        request,
        'credits/credit_report.html',
        {
            'summary': aging_summary,
            'current_bucket': current_bucket,
            'days_1_30': days_1_30,
            'days_31_60': days_31_60,
            'days_60_plus': days_60_plus,
            'active_module': 'credits',
            'active_tab': 'reports',
        },
    )


@role_required('OWNER', 'MANAGER')
def add_customer_credit_view(request):
    """
    Interface for Owners and Managers to provision, top up, or adjust customer store credit.
    Strictly restricted to OWNER and MANAGER roles. Blocked for CASHIER and CUSTOMER with 403.
    """
    user_role = getattr(request.user, 'role', None)
    if user_role not in ('OWNER', 'MANAGER'):
        if _wants_json(request):
            return _json_response(
                message='Only OWNER and MANAGER roles can provision customer credit.',
                success=False,
                status=403,
            )
        return render(
            request,
            '403.html',
            {'message': 'You do not have permission to provision customer credit.'},
            status=403,
        )

    if request.method == 'GET':
        customers_qs = (
            User.objects.filter(role='CUSTOMER', is_active=True)
            .select_related('credit_account')
            .order_by('first_name', 'last_name', 'email')
        )
        customer_list = []
        for c in customers_qs:
            acc = getattr(c, 'credit_account', None)
            customer_list.append({
                'id': c.id,
                'name': c.get_full_name() or c.username,
                'email': c.email,
                'phone': getattr(c, 'phone_number', '') or '',
                'credit_limit': str(acc.credit_limit) if acc else '0.00',
                'outstanding_balance': str(acc.outstanding_balance) if acc else '0.00',
                'available_credit': str(acc.get_available_credit()) if acc else '0.00',
                'status': acc.get_status_display() if acc else 'No Account',
            })

        if _wants_json(request):
            return _json_response(
                data={
                    'customers': customer_list,
                    'transaction_types': TRANSACTION_TYPE_CHOICES,
                },
                message='Customer credit provisioning form data retrieved.',
            )

        return render(
            request,
            'credits/add_credit.html',
            {
                'customers': customers_qs,
                'customer_list': customer_list,
                'customer_list_json': json.dumps(customer_list),
                'transaction_types': TRANSACTION_TYPE_CHOICES,
                'active_module': 'credits',
                'active_tab': 'accounts',
            },
        )

    if request.method != 'POST':
        return _json_response(message='Only GET and POST are allowed.', success=False, status=405)

    payload, parse_err = _parse_request_payload(request)
    if parse_err:
        return _json_response(message='Validation failed.', success=False, status=400, errors=parse_err)

    cust_id = payload.get('customer_id') or payload.get('customer')
    if not cust_id:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'customer_id': 'Customer is required.'},
        )

    try:
        customer = User.objects.get(pk=cust_id, role='CUSTOMER')
    except (User.DoesNotExist, TypeError, ValueError):
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'customer_id': 'Valid customer is required.'},
        )

    raw_amount = payload.get('amount')
    try:
        amount = Decimal(str(raw_amount))
        if amount <= Decimal('0.00'):
            return _json_response(
                message='Validation failed.',
                success=False,
                status=400,
                errors={'amount': 'Credit amount must be greater than zero.'},
            )
    except (TypeError, ValueError, InvalidOperation):
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'amount': 'Valid credit amount is required.'},
        )

    reason = (payload.get('notes') or payload.get('reason') or '').strip()
    if not reason:
        return _json_response(
            message='Validation failed.',
            success=False,
            status=400,
            errors={'notes': 'Manager note/reason is required.'},
        )

    tx_type = (payload.get('transaction_type') or payload.get('type') or 'TOP_UP').strip().upper()
    valid_types = {'TOP_UP', 'CREDIT_LIMIT_ADJUSTMENT', 'MANUAL_OVERRIDE'}
    if tx_type not in valid_types:
        tx_type = 'TOP_UP'

    raw_credit_limit = payload.get('credit_limit')
    specified_limit = None
    if raw_credit_limit is not None and str(raw_credit_limit).strip() != '':
        try:
            specified_limit = Decimal(str(raw_credit_limit))
            if specified_limit < Decimal('0.00'):
                return _json_response(
                    message='Validation failed.',
                    success=False,
                    status=400,
                    errors={'credit_limit': 'Credit limit cannot be negative.'},
                )
        except (TypeError, ValueError, InvalidOperation):
            return _json_response(
                message='Validation failed.',
                success=False,
                status=400,
                errors={'credit_limit': 'Valid credit limit is required.'},
            )

    with transaction.atomic():
        account, created = CreditAccount.objects.select_for_update().get_or_create(
            customer=customer,
            defaults={
                'credit_limit': Decimal('0.00'),
                'outstanding_balance': Decimal('0.00'),
                'status': CreditAccount.Status.APPROVED,
                'approved_by': request.user,
                'approved_at': timezone.now(),
                'notes': f'Store credit provisioned by {request.user.get_full_name() or request.user.email}.',
            },
        )
        if not account.approved_by:
            account.approved_by = request.user
            account.approved_at = timezone.now()
        if account.status in (CreditAccount.Status.PENDING_APPROVAL, CreditAccount.Status.REJECTED):
            account.status = CreditAccount.Status.APPROVED

        prev_balance = account.outstanding_balance
        prev_limit = account.credit_limit

        if specified_limit is not None:
            account.credit_limit = specified_limit
        elif tx_type in ('TOP_UP', 'CREDIT_LIMIT_ADJUSTMENT'):
            account.credit_limit = prev_limit + amount
        elif tx_type == 'MANUAL_OVERRIDE':
            if account.credit_limit < amount:
                account.credit_limit = amount

        account.save(update_fields=['credit_limit', 'status', 'approved_by', 'approved_at', 'updated_at'])

        tx_model_type = (
            CreditTransaction.TransactionType.CREDIT_ISSUED
            if tx_type == 'TOP_UP'
            else CreditTransaction.TransactionType.ADJUSTMENT
        )
        tx_count = account.transactions.count() + 1
        ref = f'CRD-PROV-{account.pk}-{tx_count}'

        tx = CreditTransaction.objects.create(
            credit_account=account,
            transaction_type=tx_model_type,
            amount=amount,
            previous_balance=prev_balance,
            new_balance=account.outstanding_balance,
            reference=ref,
            notes=f'[{tx_type}] {reason}',
            created_by=request.user,
        )

        customer_name = customer.get_full_name() or customer.username
        log_activity(
            actor=request.user,
            action_type=ActivityLog.ActionType.UPDATED,
            action_label='Customer credit provisioned',
            description=(
                f'Provisioned ₦{amount} credit for customer {customer_name} ({customer.email}). '
                f'Type: {tx_type}. Reason: {reason}.'
            ),
            related_object=account,
            metadata={
                'credit_account_id': account.pk,
                'customer_id': customer.pk,
                'customer_email': customer.email,
                'amount': str(amount),
                'transaction_type': tx_type,
                'previous_limit': str(prev_limit),
                'new_credit_limit': str(account.credit_limit),
                'outstanding_balance': str(account.outstanding_balance),
                'available_credit': str(account.get_available_credit()),
                'reason': reason,
                'transaction_reference': ref,
            },
        )

    success_msg = f'Successfully added ₦{amount} credit to {customer_name}.'

    if _wants_json(request):
        return _json_response(
            data={
                'account': _serialize_credit_account(account),
                'transaction': _serialize_credit_transaction(tx),
                'amount': str(amount),
                'customer_name': customer_name,
                'new_credit_limit': str(account.credit_limit),
                'available_credit': str(account.get_available_credit()),
            },
            message=success_msg,
            success=True,
            status=200,
        )

    messages.success(request, success_msg)
    return redirect('credits:credit_list')
