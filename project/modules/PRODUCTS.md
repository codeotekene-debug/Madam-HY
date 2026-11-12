# Products Module

Status: **COMPLETE / ACTIVE**

## Implemented
- Product categories
- Product catalog/list/detail (staff/management and customer storefront)
- Customer storefront views (`/customer/products/` and `/customer/products/<id>/`):
  - Category filtering, keyword search (`?q=` / `?search=`), price sorting, stock availability filtering, and pagination
  - Dual-mode response rendering: rendered HTML templates and structured JSON payloads
  - Product detail view with stock availability inspection, image resolution, and description
- Product create/update/deactivate
- Price changes/history
- Product images
- Inventory boundary behavior and stock checks
- Comprehensive API and view tests (120 passing tests in `apps.products.tests`)

## Dependencies
Inventory, Orders, Sales, Requests.

## Next
Cross-domain end-to-end purchasing regression and UI polish.

