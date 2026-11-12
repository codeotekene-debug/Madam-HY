# Security Architecture

## Authentication
Django authentication/session middleware is enabled and a custom `accounts.User` model is configured. Passwords are validated using Django's built-in validators (`UserAttributeSimilarityValidator`, `MinimumLengthValidator`, `CommonPasswordValidator`, `NumericPasswordValidator`).

## Roles
Role-based access control (RBAC) enforces five distinct system roles:
- `OWNER`: Full administrative, operational, financial, and analytics privileges.
- `MANAGER`: Management of operations, staff assignments, expense approvals, reports, and payment reconciliations.
- `CASHIER`: Point-of-sale register operations, sale recording, and repayment collection.
- `STAFF`: Operational order fulfillment, customer request handling, and shift tracking without access to financial profit or credit management.
- `CUSTOMER`: Public storefront customer with access strictly isolated to their own cart, orders, credit account, requests, and activity stream.
- `RIDER`: Dedicated delivery role restricted to rider-specific routes and deliveries assigned to that rider; cannot use management, payments, inventory, or unrelated customer data surfaces.

## Authorization & Customer Isolation
- Server-side role checks and permission decorators are enforced on every non-public view.
- Object-level customer data isolation ensures customers can never inspect, create, or mutate another customer's cart, orders, credit transactions, inquiries, or notification preferences. Tampering attempts return `403 Forbidden`.
- Privileged registration is prevented: public registration only permits the `CUSTOMER` role.
- Rider accounts are provisioned by authorized management; a rider role redirects to the rider portal and does not grant management permissions.
- Rider account creation requires a Django-validated initial password and does not use a shared default credential.

## CSRF Protection
- Django CSRF middleware (`CsrfViewMiddleware`) is enabled globally across all POST/PUT/PATCH/DELETE endpoints.
- Cookie is marked `CSRF_COOKIE_SECURE = True` in production.
- Custom navigation logout uses a secure CSRF-protected POST form.

## Production Settings & Environment Hardening
`config/settings.py` enforces production security invariants:
1. **`DEBUG` Mode**:
   - Defaults to `False` in production.
   - Evaluated safely via `env_bool("DEBUG", default=False)`.
2. **`SECRET_KEY` Protection**:
   - Strictly required from environment when `DEBUG=False`.
   - Insecure defaults (`django-insecure-*`, `change-this-to-a-random-secret-key`), keys shorter than 50 characters, and keys with low entropy (< 5 unique characters) immediately raise `ImproperlyConfigured`.
   - Local development uses fallback key only when `DEBUG=True`.
3. **`ALLOWED_HOSTS` Host Header Validation**:
   - Parsed from a comma-separated environment variable.
   - Wildcards (`'*'`) and empty host lists are disallowed when `DEBUG=False`, raising `ImproperlyConfigured`.
   - Development defaults to `['127.0.0.1', 'localhost', 'testserver']` when `DEBUG=True`.

## Security Headers & Secure Cookies Hardening
Activated by default when `DEBUG=False` with granular environment variable toggles:
- **`SECURE_BROWSER_XSS_FILTER = True`**: Enables legacy browser cross-site scripting filter.
- **`SECURE_CONTENT_TYPE_NOSNIFF = True`**: Sets `X-Content-Type-Options: nosniff` preventing MIME-type sniffing.
- **`X_FRAME_OPTIONS = 'DENY'`**: Prevents clickjacking by denying iframe rendering from any origin.
- **`SESSION_COOKIE_SECURE = True`**: Restricts session cookies exclusively to encrypted HTTPS connections in production.
- **`CSRF_COOKIE_SECURE = True`**: Restricts CSRF cookies exclusively to encrypted HTTPS connections in production.
- **`SECURE_HSTS_SECONDS = 31536000`**: Enforces HTTP Strict Transport Security for 1 year (31,536,000 seconds).
- **`SECURE_HSTS_INCLUDE_SUBDOMAINS = True`**: Cascades HSTS enforcement across all subdomains.
- **`SECURE_HSTS_PRELOAD = True`**: Enables eligibility for browser vendor HSTS preload lists.
- **`SECURE_SSL_REDIRECT = True`**: Automatically redirects HTTP requests to HTTPS in production (toggleable via `SECURE_SSL_REDIRECT`).
- **`SECURE_PROXY_SSL_HEADER`**: Configurable reverse-proxy forwarding (`('HTTP_X_FORWARDED_PROTO', 'https')`) when hosted behind Nginx, Cloudflare, or AWS ALB.

## Database Security & Routing
- **Connection URL**: Reads `DATABASE_URL` (MySQL, PostgreSQL, or SQLite) if provided.
- **Granular Credentials**: Supports `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` with `utf8mb4` charset for MySQL.
- **Local Dev Fallback**: Seamless fallback to local `db.sqlite3` out-of-the-box when running tests or development without active database servers.
- **Connection Reuse**: Configurable `CONN_MAX_AGE` for database connection pooling.

## Structured Production Logging
- Structured logging dictionary configured with console and rotating file handlers (`logging.handlers.RotatingFileHandler`).
- Disk-space bounded: 10MB per log file with 5 rotated backups in `logs/smart_shop.log`.
- Loggers configured:
  - `django`: General Django runtime logs (`INFO`).
  - `django.request`: Unhandled request exceptions (`ERROR`).
  - `django.security`: Host header failures, SuspiciousOperation, and CSRF failures (`WARNING`).
  - `apps`: Application business logs (`DEBUG` in dev, `INFO` in prod).

## Payment Security
- Never trust client-side payment status or amounts as proof of successful settlement.
- Verification layer (`PaymentVerificationService`, `BasePaymentVerifier`, `PaymentVerificationResult`) validates transaction references, positive amounts, and currency server-side.
- Payment confirmation is restricted to `OWNER` and `MANAGER` roles with row-level locks.
- Raw payment card secrets or sensitive gateway credentials must never be persisted in application models or metadata.

## Data Integrity
- Transactional atomicity (`transaction.atomic`) and row-level locking (`select_for_update`) guard credit sales, repayments, order-to-sale conversions, and expense approvals.
- Immutability guards on `ActivityLog` and approved expenses prevent post-hoc tampering of historical records.

## Automated Deployment Checks & Verification
- `python manage.py check`: 0 issues.
- `python manage.py check --deploy`: 0 issues when executed with production environment configuration.
- Comprehensive automated verification tests in `apps/accounts/tests.py` (`SecurityConfigurationTests`) covering settings validation, headers, logging handlers, and deployment checks.

## Known Security Work
- [✓] Production configuration hardening (Completed)
- [✓] Secret management verification & validation (Completed)
- [✓] Security headers & cookie hardening (Completed)
- [✓] Structured production error and security logging (Completed)
- [ ] Payment gateway live provider integration (Paystack Phase 4)
- [ ] Periodic credential rotation policy
