# Orders Module

Status: **COMPLETE / ACTIVE**

## Implemented
- Order creation/list/detail
- Customer isolation
- Management filters/search/pagination
- Lifecycle:
  PENDING → CONFIRMED → PROCESSING → READY → COMPLETED
  with supported cancellation transitions
- Order → Sale conversion with atomic credit ledger and inventory integration
- Customer Storefront Cart & Checkout Integration:
  - Session-backed `CustomerCart` manager (`apps/orders/cart.py`) handling item additions, quantity adjustments, and auto-pruning of inactive products
  - Stock boundary enforcement preventing adding or checking out more units than live inventory
  - Dual response support for cart and checkout endpoints (HTML templates and JSON APIs via `?format=json` or `Accept: application/json` / `Content-Type: application/json`)
  - Authenticated customer checkout creating `Order` in `PENDING` status without premature inventory or credit deductions
  - Strict customer isolation: Cart sessions and checkout orders strictly bound to `request.user`
  - Automated activity auditing (`ActivityLog`) and notification dispatch (`Notification`) upon successful order placement
- Credit Order checkout workflow enforcement:
  - Centralized credit eligibility and available credit verification (`CreditService.validate_credit_eligibility`)
  - Order model-level enforcement in `Order.clean()` for active/pending credit orders
  - HTTP `POST /orders/` and `POST /customer/checkout/` pre-validation and rejection of unapproved/exceeded credit requests (400 Bad Request)
  - Order-to-Sale conversion credit verification and atomic ledger recording via `Sale.complete_sale()`
  - Idempotent conversion guards preventing double credit deduction
- Notifications for selected order events
- Customer tracking UI & Customer Dashboard metrics
- Management workflow UI
- Order summary reporting (`/orders/reports/summary/`)
- Extensive model/API tests (101 passing tests in `apps.orders.tests`)

## Dependencies
Accounts, Products, Sales, Inventory, Notifications, Payments, Credits.

## Critical Rules
- Do not bypass `transition_to`.
- Do not deduct inventory merely by creating an order.
- Do not deduct credit balance merely by creating an order (order creation is a pending transaction; credit is deducted only upon completion/conversion to Sale).
- Preserve item snapshots.
- Preserve customer isolation.
- Preserve Order → Sale atomic transaction behavior.

## Known Integration Gap
Payment records are safely linkable to an existing Order through the Payments service/API boundary without altering the Order lifecycle. This remains a record-only integration; it does not transform the Order into a Sale or change fulfillment/inventory behavior. Credit orders consume credit upon conversion to Sale.


