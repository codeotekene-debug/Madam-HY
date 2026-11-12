# Smart Shop Roadmap

Legend:
- `[✓]` implemented/verified
- `[~]` partial
- `[ ]` not complete
- `[!]` needs investigation

## Current Priority
**Section 18 Production Packaging, Dockerization & Staging Deployment Completed.**

MADAM HY Smart Shop is fully packaged for production with multi-stage Docker containers, docker-compose orchestration, systemd service units, high-security Nginx TLS reverse proxying, zero-downtime deployment automation, and daily database backup routines. The system is hardened and staging-ready.

## 1. Foundation
- [✓] Django project
- [✓] Custom User model and roles
- [✓] MySQL configuration
- [✓] Core frontend structure
- [✓] Dedicated Staff Portal Login (`/accounts/portal/login/`) & clean Customer Login (`/accounts/login/`) with automated dashboard routing
- [✓] Public storefront registration (`/accounts/register/`) strictly enforcing `CUSTOMER` role without account type selector

## 2. Products
- [✓] Product/category models
- [✓] Product management APIs
- [✓] Product images
- [✓] Price history
- [✓] Tests
- [✓] Final UI/API integration review (customer catalog, category filter, search, detail)


## 3. Inventory
- [✓] Inventory model
- [✓] Stock adjustment
- [✓] Stock movements
- [✓] Inventory reports
- [✓] Tests
- [~] Final UI integration review

## 4. Sales
- [✓] Sale model
- [✓] POS sale creation
- [✓] Sale completion
- [✓] Payment validation during sale completion
- [✓] Inventory deduction on completion
- [✓] Sales reporting
- [~] Dedicated Payments lifecycle integration review
- [✓] Credit workflow integration (POS sales)
- [!] Historical cost/profit methodology requires deliberate decision

## 5. Orders
- [✓] Orders API foundation
- [✓] Customer order creation/list/detail
- [✓] Lifecycle transitions
- [✓] Order → Sale conversion
- [✓] Selected notification events
- [✓] Customer tracking
- [✓] Management workflow
- [✓] Order summary reporting
- [~] Final Payments integration review
- [✓] Credit workflow integration (checkout & conversion)

## 6. Payments
- [✓] Payment model
- [✓] Payment constraints/validation
- [✓] Payment service layer
- [✓] Payment HTTP API (list/create/detail)
- [✓] Payment authorization/isolation
- [✓] Safe Order integration (record-only)
- [✓] Safe Sale integration (record-only)
- [✓] Payment aggregation / balance calculation
- [✓] Payment creation idempotency
- [✓] Payment confirmation (PENDING → COMPLETED only)
- [✓] Read-only reconciliation service/classifications
- [✓] Read-only reconciliation API endpoints & views (Phase 2)
- [✓] Broader reconciliation workflow/UI (overview & details)
- [✓] Provider-neutral verification layer & mock verifiers (Phase 3)
- [✓] Role-gated verification API endpoint & activity audit (`/payments/<id>/verify/`)
- [✓] Paystack online verification adapter & multi-channel scaffolding (Phase 4A)
- [✓] Moniepoint POS terminal verification adapter (Phase 4B)
- [✓] In-Store counter dynamic QR payment generation & verification (Phase 4C)
- [✓] Paystack & Moniepoint webhook ingestion & double-payment guards (Phase 5)
- [✓] Automated payment reconciliation & mismatch resolution actions (Phase 6)
- [✓] Refunds, chargebacks, & multi-channel reversal workflows (Phase 7)
- [~] Payment UI/API integration completion
- [ ] Deliberate resolution of Sale/Order payment lifecycle semantics

## 7. Credits
- [✓] Credit models
- [✓] Core credit business-rule/service foundation
- [✓] POS credit-sale enforcement and atomic ledger integration
- [✓] Customer Order credit enforcement (Order checkout & conversion)
- [✓] Credit API (list, detail, customer view, manager actions)
- [✓] Credit UI integration (credits.html, credit_detail.html, credit_payment.html)
- [✓] Repayment workflow (atomic ledger repayment service, form, views, API)
- [✓] Credit reporting integration verification

## 8. Expenses
- [✓] Expense model
- [✓] Expense business rules
- [✓] Expense API & HTTP views
- [✓] Expense approval workflow & activity audit
- [✓] Expense UI integration (expenses.html, add_expense.html, expense_detail.html)

## 9. Reports
- [✓] Reporting service foundation
- [✓] HTTP/API layer (sales, expenses, profit, growth, summary)
- [✓] Dashboard integration (reports.html, sales_report.html, expense_report.html, profit_report.html, growth.html)
- [~] Historical costing/profit methodology finalization
- [✓] Final profit/loss presentation
- [ ] Export/report delivery

## 10. Notifications
- [✓] Notification model
- [✓] Notification service
- [✓] Orders event integration
- [✓] Notification API (inbox, unread count, mark-read, mark-all-read)
- [✓] Notification center UI & navbar badge counter integration
- [✓] Broader event coverage (orders, payments, requests, credit repayments)

## 11. Requests
- [✓] Request model
- [✓] Request API (create, list, detail, customer views, manager updates)
- [✓] Request management UI (requests.html, request_detail.html, create_request.html)
- [✓] Customer request workflow (customer/requests.html, customer/request_detail.html)

## 12. Activity Logs
- [✓] ActivityLog model/service
- [✓] API/UI audit viewer (`/activity-logs/` list & detail, filters, modal/JSON)
- [✓] Broader event coverage (orders, payments, repayments, expenses, requests, customer preferences)

## 13. Customer Portal
- [✓] Templates and scripts exist
- [✓] Product browsing/cart/order surfaces
- [✓] Clean Customer Login form (`/accounts/login/`) without role selector, with discreet Staff Portal link
- [✓] Public Customer Registration form (`/accounts/register/`) without role selector, strictly enforcing `CUSTOMER` role and ignoring privileged role payloads
- [✓] Customer Notification delivery preferences & settings API (`/customer/settings/`)
- [✓] Customer Dashboard live metrics & activity aggregation (`/customer/` and `/customer/dashboard/`)
- [✓] Full API integration across all customer features (catalog browsing, session cart, credit-checked checkout)

## 14. Management Portal
- [✓] Templates and scripts exist
- [✓] Dedicated Staff Portal Login (`/accounts/portal/login/` & `/portal/login/`) with customer access rejection (403) and staff dashboard routing
- [✓] Orders management workflow
- [✓] Sales/inventory/products integration
- [✓] Expenses, Credits, Reports, Requests, and Activity Logs management workflows
- [✓] Management Operations Dashboards (Owner & Staff live views, dual HTML/JSON, strict RBAC, isolation)


## 15. UI/UX Completion
- [✓] Shared design system (MADAM HY tokens in variables.css, base.css, components.css, forms.css, sidebar.css, navbar.css, tables.css, modals.css)
- [✓] Responsive structure (Fluid grid/flex layouts, mobile-drawer sidebar, table-responsive touch scroll, modal-container viewport sizing)
- [✓] Remove remaining demo/placeholder behavior (Comprehensive codebase audit: eliminated hardcoded accounts/credentials like '8012345678', static mock datasets/charts, fake delays, external image placeholders, dead href="#" links, and wired real production endpoints/webhooks across backend, templates, and frontend scripts)
- [✓] Replace placeholder navigation (Role-gated URL routing in base.html across sidebar, topbar, and mobile drawer)
- [✓] Custom error handling & branding (403 Forbidden, 404 Not Found, 500 Server Error with dual HTML/JSON content negotiation)
- [✓] Accessibility pass (WCAG 2.1 AA color contrast >= 4.5:1, skip-link, visible :focus-visible outlines, ARIA labels, landmarks, modal focus-trapping)
- [✓] Mobile/tablet/desktop QA (Minimum 44x44px touch targets on buttons, drawer links & inputs, zero horizontal clipping, responsive dialogs)
- [✓] Consistency pass (Standardized badges, alert boxes, cards, and data table layouts to design tokens)

## 16. Security & Production Hardening
- [✓] Authentication/authorization foundation (custom User model, RBAC roles, customer isolation)
- [✓] Production secret management (strict SECRET_KEY validation, >=50 chars, entropy check, rejection of defaults)
- [✓] DEBUG production hardening (defaults to False, environment variable parsing)
- [✓] Security headers & cookies hardening (HSTS 1-year/subdomains/preload, SSL redirect, secure session/CSRF cookies, X-Frame-Options DENY, nosniff, XSS filter)
- [✓] Structured production error and security logging (RotatingFileHandler, django.security)
- [✓] Production database routing & connection handling (DATABASE_URL, MySQL, SQLite local fallback)
- [✓] Automated deployment checks (`python manage.py check --deploy` passes with 0 issues)
- [✓] Payment provider verifiers, dynamic counter QR & webhooks (Paystack Phase 4A, Moniepoint POS Phase 4B, Dynamic QR Phase 4C, Webhooks Phase 5)
- [ ] Credential rotation policy

## 17. Final Integration
- [✓] End-to-end customer purchase (Catalog browsing -> session cart -> credit-checked checkout -> Paystack webhook confirmation -> conversion to sale)
- [✓] End-to-end POS sale (Cashier multi-item checkout -> in-store dynamic QR generation -> Moniepoint webhook confirmation -> sale finalization & atomic stock deduction)
- [✓] Payment reconciliation workflow (Idempotent webhook ingestion, double-payment prevention, discrepancy resolution via PaymentResolutionService)
- [✓] Inventory integrity (Strict atomic stock decrements via adjust_inventory_stock on completion, StockMovement audit records, restocking on return)
- [✓] Credit workflow (Credit eligibility checks, credit-sale atomic ledger recording, partial repayments, overpayment resolution with credit limit expansion)
- [✓] Reports consistency (Sales summaries, daily/monthly revenue metrics, cashier transaction isolation, P&L reporting)
- [✓] Notifications (Multi-channel in-app customer notifications for order placement, payment confirmations, and refunds)
- [✓] Audit logs (Comprehensive ActivityLog entries for payments, webhooks, discrepancies, and state transitions)
- [✓] Full regression test suite (772 automated tests passing across all apps and end-to-end integration pass suite)

## 18. Packaging & Staging Deployment
- [✓] Multi-stage production Dockerfile (`deploy/docker/Dockerfile` with Python 3.12, unprivileged user, multi-stage wheel cache)
- [✓] Production Docker Compose orchestration (`deploy/docker/docker-compose.prod.yml` with MySQL 8.0, Gunicorn, Nginx, healthchecks & volumes)
- [✓] Automated container entrypoint (`deploy/docker/entrypoint.sh` with database wait-loop, migrations & collectstatic)
- [✓] High-security Nginx reverse proxy configuration (`deploy/nginx/smart_shop.conf` with TLS 1.2/1.3, HTTP 301 redirect, 30d asset caching)
- [✓] Docker Nginx configuration (`deploy/nginx/smart_shop_docker.conf` proxying to `web:8000`)
- [✓] Systemd service unit (`deploy/systemd/smart_shop.service` with process monitoring, sandbox isolation, graceful SIGHUP reloads)
- [✓] Zero-downtime deployment automation script (`deploy/scripts/deploy.sh` with pre-flight checks, automated backup, dependency sync, migrations, and reload)
- [✓] Automated database backup routine (`deploy/scripts/backup_db.sh` with mysqldump, atomic transaction snapshot, gzip compression, and 14-day retention pruning)
- [✓] Hardened production environment template (`.env.production.example` with DEBUG=False, strict SSL/HSTS, and secure cookie defaults)



## 19. Rider and Delivery Management
- [x] Phase 1 audit: verified existing role, delivery app, order/payment/inventory boundaries, stale documentation, and missing rider templates/tests.
- [x] Phase 2 foundation: RIDER account role, rider profile validation, delivery data model, assignment history model, migration, and foundation tests.
- [ ] Phase 3 service integration: record assignments, reassignments, acceptance/rejection, and transitions atomically with role checks and tests.
- [ ] Phase 4 management delivery dashboard and rider administration UI.
- [ ] Phase 5 responsive rider portal and actions.
- [ ] Phase 6 customer delivery tracking.
- [ ] Phase 7 secure OTP delivery confirmation and exception handling.
- [ ] Phase 8 configured delivery zones, fees, and checkout totals.
- [ ] Phase 9 notifications, reports, and activity audit integration.
- [ ] Phase 10 end-to-end testing, security review, and production hardening.
- Current source already has service/view scaffolding for several later phases, but missing templates and tests mean those phases are not complete.


### Delivery system remaining acceptance
- Implemented rider and management UI, checkout zone fee snapshots, assignment history, OTP hardening, customer tracking, and dispatch checks (2026-11-04).
- Remaining before production: full project test suite, browser/accessibility review, production zone/support configuration, and validation of external notification delivery.
