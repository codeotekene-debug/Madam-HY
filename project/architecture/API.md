# API Architecture

## Main Prefixes
- `/accounts/`
- `/products/`
- `/inventory/`
- `/sales/`
- `/orders/`
- `/payments/`
- `/credits/`
- `/expenses/`
- `/reports/`
- `/requests/`
- `/preview/`

## Active Backend Endpoints

### Accounts
- `POST /accounts/login/`
- `POST /accounts/logout/`
- `POST /accounts/register/`
- `GET/POST /accounts/profile/`
- `POST /accounts/change-password/`

### Products
Catalog, product management, image management and category management endpoints are implemented.

### Inventory
- `/inventory/`
- `/inventory/reports/summary/`
- `/inventory/reports/movements/`
- `/inventory/reports/low-stock/`
- `/inventory/<id>/adjust/`
- `/inventory/<id>/movements/`
- `/inventory/<id>/`

### Sales
- `/sales/`
- `/sales/reports/summary/`
- `/sales/<id>/complete/`
- `/sales/<id>/`

### Orders
- `/orders/` — GET list / POST create
- `/orders/reports/summary/`
- `/orders/<id>/`
- `/orders/<id>/status/`
- `/orders/<id>/convert-to-sale/`

### Delivery (partial; end-to-end contract not yet verified)
- `/rider/` and `/rider/...` — rider portal views and action endpoints are wired in `apps.delivery.urls`.
- `/deliveries/...` — management delivery views and assignment/configuration endpoints are wired.
- `/api/delivery/zones/` and `/api/delivery/track/<order_ref>/` — public zone and customer tracking endpoints are wired.
- Rider and management templates are not present yet; do not treat the HTML views as a complete working portal until those pages and endpoint tests are implemented.

### Payments
Implemented endpoints:
- `GET /payments/` — list payments with authentication and customer-scoped access checks
- `POST /payments/` — create a payment record for a sale or order
- `GET /payments/<id>/` — retrieve an individual payment record
- `POST /payments/<id>/confirm/` — confirm a pending payment for authorized management users
- `GET /payments/reconciliation/order/<order_id>/` — read-only order financial reconciliation for management (`OWNER`, `MANAGER`)
- `GET /payments/reconciliation/sale/<sale_id>/` — read-only sale financial reconciliation for management (`OWNER`, `MANAGER`)

`POST /payments/` accepts the optional `X-Idempotency-Key` header. The key is trimmed and must be at most 120 characters. A repeated request with the same key and identical payment data returns the existing Payment and does not create another record. Reusing the key with different payment data returns HTTP 400. The key applies to both Order and Sale payments.

`POST /payments/<id>/confirm/` requires an authenticated `OWNER` or `MANAGER`. It permits only `PENDING` → `COMPLETED`; repeating the request for an already completed Payment is idempotent. It does not change Order, Sale, inventory, credit, or notification state.

`GET /payments/reconciliation/order/<order_id>/` and `GET /payments/reconciliation/sale/<sale_id>/` require an authenticated `OWNER` or `MANAGER` (401 for unauthenticated, 403 for `CASHIER`, `STAFF`, `CUSTOMER`). These endpoints are strictly read-only and GET-only (405 for POST/PUT/PATCH/DELETE). They return transaction balance totals, payment counts by status, 2-decimal monetary strings, classification (`UNPAID`, `PARTIALLY_PAID`, `FULLY_PAID`, `OVERPAID`), and inconsistency findings without modifying any records. Malformed or nonexistent IDs return HTTP 404.

Future functionality:
- frontend UI integration for reconciliation workflows
- provider integration and gateway/webhook support

### Credits / Expenses / Reports / Requests
Models/services exist in varying degrees, but their URL/view layers are currently incomplete or empty.

## Contract Rules
- Use explicit status codes.
- Validate input server-side.
- Do not trust frontend role checks.
- Preserve customer isolation.
- Do not change established response structures without checking consumers/tests.
