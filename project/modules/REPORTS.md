# Reports Module

Status: **COMPLETE / PRODUCTION-READY HTTP VIEWS & API**

## Implemented
- Core Services (`apps/reports/services.py`):
  - Normalized date range resolution (`get_date_range`): supports `today`, `this_week`, `week`, `this_month`, `month`, `this_year`, `year`, and ISO `custom` date strings with range validation
  - Financial Decimal quantization helper (`_to_money`): standardizes all currency figures to `Decimal('0.01')` across models and queries
  - Sales report (`sales_report`): aggregated revenue, transaction count, average sale, sales by day, sales by payment method, sales by cashier, top-selling products, and category totals (strictly for `COMPLETED` sales)
  - Expense report (`expense_report`): aggregated spending, category breakdown, payment method distribution, daily breakdown, largest expenses, and recent expense line items; filters strictly by `APPROVED` expenses by default
  - Profit & Loss report (`profit_report`): revenue, cost of goods sold (COGS), gross profit, approved operating expenses, net profit, and profit margin
  - Growth report (`growth_report`): week-over-week, month-over-month, and year-over-year percentage comparisons for sales revenue, approved expenses, net profit, and sales transaction volume
  - Inventory summary (`inventory_summary`): total product count, in-stock count, low stock alert count, out-of-stock count, total quantity, and stock valuation
  - Credit summary (`credit_summary`): total credit limit, outstanding balances, available credit, active/overdue accounts, and period repayments
- HTTP Views & API Endpoints (`apps/reports/views.py` & `apps/reports/urls.py`):
  - `reports_dashboard` (`GET /reports/`): Overview metrics (today's revenue, net profit, monthly approved expenses, low stock alert summary) rendering `reports/reports.html` or returning JSON payload (`?format=json` or `Accept: application/json`)
  - `sales_report_view` (`GET /reports/sales/`): Detailed breakdown of sales by date range, payment methods, and top products rendering `reports/sales_report.html` or returning JSON
  - `expense_report_view` (`GET /reports/expenses/` and `/reports/expense/`): Approved expense category breakdown, vendor summary, and trends rendering `reports/expense_report.html` or returning JSON
  - `profit_report_view` (`GET /reports/profit/`): Net profit calculations (Gross Sales - COGS - Approved Expenses) rendering `reports/profit_report.html` or returning JSON
  - `growth_report_view` (`GET /reports/growth/`): Sales and order volume growth comparisons rendering `reports/growth.html` or returning JSON
- Security & Role-Based Access Control (RBAC):
  - Strictly limited to `OWNER` and `MANAGER` roles
  - Rejects `CASHIER`, `STAFF`, and `CUSTOMER` with 403 Forbidden
  - Rejects unauthenticated requests with 401 Unauthorized for API/JSON or redirects to login for HTML requests
- Audit Logging:
  - Logs report access via `apps.activity_logs.services.log_activity` with `ActivityLog.ActionType.VIEWED`
- Comprehensive Test Suite (`apps/reports/tests.py`):
  - 44 passing tests covering service calculations, SQLite date handling, approved-expense filtering, RBAC permissions, period/custom date filtering, payment/category filtering, JSON serialization, HTML rendering, and audit logging

## Missing
- Broader reports export (CSV/Excel/PDF download) integration review

## Next
Requests management & customer workflow (or Notifications center integration).
