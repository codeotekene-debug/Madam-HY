# Credits Module

Status: **CORE HTTP APIS & REPAYMENT WORKFLOW IMPLEMENTED / PRODUCTION-READY FOUNDATION**

## Implemented
- `CreditAccount` model and constraints
- `CreditTransaction` model and ledger constraints
- Centralized `CreditService` (`apps/credits/services.py`):
  - `get_credit_account(customer)`: retrieves credit account for user with role `CUSTOMER`
  - `validate_credit_eligibility(customer, amount)`: validates active/approved status, manager approval, and sufficient credit limit
  - `process_credit_sale(sale, created_by)`: atomically records `CREDIT_PURCHASE` ledger transaction and updates account balance with row-locking; dynamically incorporates source order references
  - `process_repayment(credit_account, amount, payment_method, created_by, reference, notes, payment)`: atomically records `REPAYMENT` ledger transaction with row-level locking (`select_for_update`), balance deduction, status transition (`APPROVED` when fully cleared), and historical audit logging via `log_activity`
- Forms & Validation (`apps/credits/forms.py`):
  - `CreditRepaymentForm`: enforces strictly positive repayment amounts, balance limits (`amount <= outstanding_balance`), and payment method normalization (`CASH`, `BANK_TRANSFER`, `CARD`, `POS`, `TRANSFER`)
- Credit HTTP Views & Endpoints (`apps/credits/views.py` & `apps/credits/urls.py`):
  - `credit_account_list` (`GET /credits/`, `/credits/accounts/`): filterable by customer search, status, and positive balance (`has_balance=true`); aggregates summary metrics (`total_issued`, `total_outstanding`, `total_overdue`, `total_accounts`); strictly enforces customer isolation (customers only see their own account)
  - `credit_account_detail` (`GET /credits/accounts/<id>/`, `/credits/<id>/`): returns limit, balance, available credit, overdue metrics, and ledger history of transactions; enforces object-level customer isolation and logs audit views
  - `credit_repay` (`POST /credits/accounts/<id>/repay/`, `/credits/<id>/repay/`): authorized staff endpoint (`OWNER`, `MANAGER`, `CASHIER`) for recording repayments; rejects unauthenticated (401), customer role submissions (403), invalid methods or amounts exceeding balance (400)
  - Template helper pages: `credit_payment_page` (`GET /credits/payment/`) and browser template rendering for `credits.html` and `credit_detail.html`
- Direct POS Sales credit enforcement in `Sale.complete_sale()`:
  - Strict customer requirement (`role=CUSTOMER`)
  - Pre-inventory eligibility and credit-limit check
  - Atomic inventory deduction
  - Atomic ledger transaction recording (`CreditTransaction`)
  - Atomic rollback across inventory, sale, and credit account on any failure
- Customer Orders credit checkout workflow enforcement:
  - Model-level validation in `Order.clean()` for active/pending credit orders
  - HTTP `POST /orders/` credit eligibility pre-validation before order creation
  - Order → Sale conversion validation before `Sale` creation
  - Conversion execution via `Sale.complete_sale()` consuming credit, logging `CreditTransaction`, and deducting inventory atomically
  - Concurrency/double-deduction guards via row-level locks, status checks, and `OneToOneField` constraint
- Comprehensive Test Coverage (`apps/credits/tests.py`):
  - 46 total passing tests in `apps.credits.tests` covering models, service logic, atomic balance updates, RBAC, customer isolation, input validation, and HTTP endpoints.

## Missing
- Customer-facing payment gateway integration (e.g., Paystack self-service online repayment)
- Final credit reporting integration review

## Next
Expenses HTTP API and reporting workflow (or Reports / Analytics foundation).
