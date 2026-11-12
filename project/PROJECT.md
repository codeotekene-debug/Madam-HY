# Smart Shop — Product & Architecture

## Product
MADAM HY Smart Shop is a Django-based shop management and customer shopping platform intended to support physical shop operations, customer ordering, inventory, sales, payments, credits, expenses, reporting, notifications, requests, and audit activity.

## Stack
- Python
- Django
- MySQL
- HTML/CSS/JavaScript
- Django sessions/authentication
- Static CSS and page/AJAX JavaScript
- Media storage for product images

## User Roles
- OWNER
- MANAGER
- CASHIER
- STAFF
- CUSTOMER
- RIDER

## Django Apps
`accounts`, `products`, `inventory`, `sales`, `orders`, `payments`, `credits`, `expenses`, `reports`, `requests`, `notifications`, `activity_logs`, `delivery`, plus `preview`.

## Major Business Flow
Customer/Staff
→ Product
→ Order or POS Sale
→ Payment
→ Inventory effects at fulfillment/completion
→ Reports
→ Notifications/Audit activity

Orders and POS Sales are separate concepts. Orders can be converted to Sales.

## Architectural Principle
The current code is authoritative. Documentation records what exists and what remains; it must not invent implementation.

## Frontend
Templates live under `templates/`.
Core CSS lives under `static/css/core/`.
Page CSS lives under `static/css/pages/`.
Core JavaScript lives under `static/js/core/`.
Page JavaScript lives under `static/js/pages/`.
AJAX helpers/scripts live under `static/js/ajax/`.

## Design Direction
MADAM HY uses a green-centered retail design. The interface is intended to be clean, modern, professional, simple, responsive, and usable on desktop, tablet, and mobile.

## Important Constraints
- Customer data must remain isolated.
- Role authorization must be enforced server-side.
- Historical financial/inventory records should not be casually deleted.
- Order price snapshots must preserve historical accuracy.
- Order lifecycle rules must remain explicit.
- Inventory must not be changed accidentally by merely creating an order.
- Payment records must not become an uncontrolled second source of truth for credit/inventory accounting.
