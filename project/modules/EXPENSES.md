# Expenses Module

Status: **COMPLETE / PRODUCTION-READY HTTP WORKFLOW & APPROVALS**

## Implemented
- `Expense` model enhancements:
  - Added `uuid` identifier for safe external/API lookup
  - Added `status` field (`PENDING`, `APPROVED`, `REJECTED`)
  - Added audit fields: `approved_by`, `approved_at`, `rejection_reason`, and `receipt_image`
  - Protection against modifying or deleting approved expense records
  - Strictly positive amount validation (`amount > 0`)
  - Migration `0002_expense_approved_at_expense_approved_by_and_more` applied cleanly
- `ExpenseService` (`apps/expenses/services.py`):
  - `create_expense`: records expense in `PENDING` status, normalizes categories and payment methods, assigns `recorded_by`, auto-generates references, and logs creation audit via `log_activity`
  - `approve_expense`: validates approver permissions (`OWNER`, `MANAGER`), locks expense row, updates status to `APPROVED`, sets timestamps, and logs approval audit via `log_activity`
  - `reject_expense`: validates approver permissions (`OWNER`, `MANAGER`), locks expense row, records rejection reason, updates status to `REJECTED`, and logs rejection audit via `log_activity`
  - `get_expense_summary`: aggregates total spending, approved totals, pending counts, monthly/annual metrics, and top category breakdown
- Forms & Validation (`apps/expenses/forms.py`):
  - `ExpenseForm`: validates category, positive amount, date incurred, vendor, payment methods, description, receipt image, and notes
  - `ExpenseRejectionForm`: captures rejection reasons for management workflow
- Production HTTP Views & Endpoints (`apps/expenses/views.py` & `apps/expenses/urls.py`):
  - `expense_list` (`GET /expenses/`, `/expenses/list/`): paginated list supporting date range, category, status, and search filters; aggregates spending cards; scopes visibility (`STAFF`/`CASHIER` view only their recorded expenses; `OWNER`/`MANAGER` view all; `CUSTOMER` denied with 403)
  - `expense_create` (`GET`/`POST /expenses/add/`, `/expenses/create/`): dual JSON and HTML form support for recording new expenses; validates and persists attachments and auto-assigns creator
  - `expense_detail` (`GET /expenses/<uuid:id>/`, `/expenses/<str:id>/`): detailed record inspection with audit stamps and receipt attachment; enforces role scoping and logs audit views
  - `expense_approve` (`POST /expenses/<uuid:id>/approve/`, `/expenses/<str:id>/approve/`): management-only approval action (`OWNER`, `MANAGER`)
  - `expense_reject` (`POST /expenses/<uuid:id>/reject/`, `/expenses/<str:id>/reject/`): management-only rejection action (`OWNER`, `MANAGER`) with optional reason
  - Seamless template integration with `expenses.html`, `add_expense.html`, and `expense_detail.html`
- Comprehensive Test Suite (`apps/expenses/tests.py`):
  - 41 passing tests covering models, service methods, validation constraints, RBAC permissions, customer isolation, pagination, filters, and approval/rejection endpoints.

## Missing
- Broader reports/analytics export (CSV/Excel/PDF) integration review

## Next
Reports / Analytics backend aggregation foundation (or Orders/Sales payment lifecycle reconciliation review).
