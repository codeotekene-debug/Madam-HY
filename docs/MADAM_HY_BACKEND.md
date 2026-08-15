# MADAM HY Backend Architecture

## 1. Project Overview

MADAM HY is a Django-based retail and customer commerce system for a physical shop with customer-facing online browsing and product-request workflows. The repository is structured as a Django project with multiple application modules, while the frontend is already implemented as Django templates, HTML, CSS, and JavaScript assets.

The backend is intended to support the same business domain as the frontend, but implementation proceeds incrementally. The current repository confirms that the backend foundation is already in place for Accounts and Products, while the remaining business modules remain planned.

Current stack confirmed by the repository:

- Django
- MySQL
- Django ORM
- Django authentication
- Django templates
- HTML/CSS/JavaScript frontend

This document is the source of truth for future backend work. It does not describe future features as implemented unless the repository actually contains them.

## 2. Architecture Principles

The backend follows a modular Django app structure, with each domain owning its own responsibilities. The project is organized around domain apps rather than a single large application. This keeps models, services, views, and logic separated by responsibility.

Core backend principles:

- Modular Django apps for business domains
- Separation of concerns between product data, inventory data, sales data, orders, payments, credits, expenses, and reporting
- Use of Django ORM for persistence and relationships
- DecimalField for all monetary values
- Historical financial records for price and related financial changes when history matters
- Database constraints for rules that can be enforced at the database level
- Model validation where database constraints are not sufficient or practical
- No unnecessary data duplication
- Inventory separated from product definitions
- Reports derived from transactional datasets rather than duplicated summary tables
- Incremental implementation of backend phases in order

## 3. Business Rules

The following business rules are confirmed by the project requirements and repository context:

1. OWNER has full system access.
2. MANAGER, CASHIER, STAFF, and CUSTOMER have restricted access.
3. Customers can purchase through the customer website.
4. Customers can only purchase using credit if they have an approved credit allowance.
5. Staff are not assigned to orders.
6. The business currently operates one shop/location.
7. Products support multiple images.
8. Product price changes preserve historical pricing.
9. Important financial and business actions should eventually be auditable.
10. Supported payment methods are:
   - CASH
   - BANK_TRANSFER
   - CARD
   - CREDIT

No additional business rules are introduced here unless they are confirmed by the repository or explicit project requirements.

## 4. Roles and Access

The backend uses the following roles:

- OWNER
- MANAGER
- CASHIER
- STAFF
- CUSTOMER

Role handling is centered on the custom Accounts user model. The repository confirms the role choices and related helper methods in the Accounts model.

OWNER:
- unrestricted access

Other roles:
- restricted according to their responsibilities

Detailed permissions will be implemented in later backend phases. Access checks should be centralized and avoid being scattered across unrelated models.

## 5. Backend Modules

The project is organized into distinct backend modules, each owning a specific business boundary.

### Accounts
Status: COMPLETE

Accounts owns authentication, user identity, role assignment, and customer profile data. It includes the custom User model, CustomerProfile, admin configuration, and authentication settings integration.

### Products
Status: COMPLETE

Products owns product identity, categories, SKU, base product information, product images, pricing, and historical price changes. It does not own stock quantities or inventory movement records.

### Inventory
Status: PLANNED

Inventory will own stock quantities, stock movements, stock adjustments, low-stock calculations, and out-of-stock calculations. Inventory should not duplicate product definition data.

### Sales / POS
Status: PLANNED

Sales/POS will eventually own sales transactions, sale items, discounts, and transaction totals. This is a future backend phase and not implemented in the repository.

### Orders
Status: PLANNED

Orders will own customer orders, order items, and lifecycle/status tracking. Staff are not assigned to orders. This boundary is planned for a later phase.

### Payments
Status: PLANNED

Payments will own payment records, payment methods, payment status, and payment references. Supported methods are CASH, BANK_TRANSFER, CARD, and CREDIT. Real payment gateway integration is a later phase.

### Credits
Status: PLANNED

Credits will eventually own credit allowances, credit usage, outstanding balances, repayments, due dates, and credit status. Customers cannot use credit automatically; they require an approved credit allowance.

### Expenses
Status: PLANNED

Expenses will own business expenses, expense categories, and expense records.

### Requests
Status: PLANNED

Requests will own product and customer request records and request status workflows.

### Reports
Status: PLANNED

Reports must derive from source transactional data. Sales reports should come from sales records, profit reports from sales and cost records plus expenses, credit reports from credit data, and inventory reports from inventory records.

### Notifications
Status: PLANNED

Notifications will manage system and customer alerts when implemented.

### Activity Logs
Status: PLANNED

Important business and financial actions should eventually be auditable. Examples include sale creation, payment recording, credit granting, product price updates, expense recording, and stock adjustments.

### Customer functionality
Status: PLANNED

Customer-facing functionality includes customer browsing, product selection, checkout flows, order history, request submission, credit usage rules, and customer profile management. This is not considered implemented unless the corresponding backend layer exists in the repository.

## 6. Current Implementation Status

### Accounts
Status: COMPLETE

The repository contains an Accounts backend foundation with the following verified implementation details:

- Custom user model defined as accounts.User
- Role choices for OWNER, MANAGER, CASHIER, STAFF, and CUSTOMER
- Email-based authentication with unique email and custom username/email configuration
- phone_number field with validation
- created_at and updated_at timestamps
- CustomerProfile model using OneToOneField to the user
- Admin registration for user and customer profile
- AUTH_USER_MODEL set to accounts.User in the project settings
- Django migration files present under apps/accounts/migrations
- Custom admin behavior for role-based user management

This is the confirmed backend foundation already present in the repository.

### Products
Status: COMPLETE

The repository contains an implemented Products backend foundation with the following verified details:

- ProductCategory model
- Product model
- ProductImage model
- ProductPriceHistory model
- Unique SKU enforcement on Product
- DecimalField pricing for selling_price and cost_price
- reorder_level field on Product
- Product image support for multiple images per product
- Primary image concept enforced per product
- display_order for image ordering
- Historical tracking of selling price changes through ProductPriceHistory
- Tracking of previous price, new price, changed_by, reason, and changed_at
- Django admin configuration for categories, products, images, and price history
- Product migration files present in apps/products/migrations
- Product tests covering uniqueness, multiple images, primary-image enforcement, historical pricing, negative-price validation, and Django checks

The repository confirms these actual product boundaries:

- Product owns product identity, category, SKU, pricing, images, price history, and reorder level.
- Product does not own current stock quantity, stock movements, stock adjustments, or an inventory ledger.
- Inventory is explicitly separated from product records.

### Other modules
Status: PLANNED

The following modules are present as app folders in the repository structure, but there is no verified backend implementation proving they are complete:

- Inventory
- Sales
- Orders
- Payments
- Credits
- Expenses
- Requests
- Reports
- Notifications
- Activity Logs
- Customer backend integration

These modules remain planned until they are implemented and verified in the repository.

## 7. Database Design Principles

The backend should follow clear database design principles:

- Use Django ORM models and migrations for persistence.
- Use DecimalField for all monetary values.
- Use ForeignKey for one-to-many relationships.
- Use OneToOneField only where the relationship is truly one-to-one.
- Use ManyToManyField only when the relationship genuinely requires it.
- Add timestamps to important business records.
- Add indexes for meaningful query patterns.
- Use meaningful related_name values for reverse relationships.
- Use database constraints where appropriate.
- Use model validation where business rules cannot be enforced reliably at the database layer.
- Preserve historical records when losing earlier values would be incorrect.
- Avoid unnecessary duplication of data.
- Preserve existing data during migrations and future changes.

## 8. Product Boundary

This boundary is critical and is already reflected in the repository.

Products own:

- product identity
- category
- SKU
- pricing
- product images
- price history
- reorder level

Products do not own:

- current stock quantity
- stock movements
- stock adjustments
- inventory ledger

Inventory owns stock.

This distinction is required to keep product records stable and inventory records separate from product definitions.

## 9. Inventory Boundary

Status: NEXT

The next backend phase is Inventory Foundation.

Inventory will own:

- stock quantities
- stock movements
- stock adjustments
- low-stock calculations
- out-of-stock calculations

Inventory must not duplicate product information unnecessarily. It should track stock state and stock movement records while product records remain the canonical catalog data.

## 10. Sales / POS Boundary

Sales/POS will eventually own:

- sales transactions
- sale items
- discounts
- transaction totals

This is a future phase and should not be implemented before the inventory, sales, and payment boundaries are clearly defined and reviewed.

## 11. Orders Boundary

Orders will own:

- customer orders
- order items
- order lifecycle/status

Staff are not assigned to orders. This rule is a confirmed business requirement and should be enforced in the future orders backend design.

## 12. Payments Boundary

Payments will own:

- payment records
- payment methods
- payment status
- payment references

Supported payment methods:

- CASH
- BANK_TRANSFER
- CARD
- CREDIT

Real payment gateway integration is a later phase. The backend should not assume third-party gateway integration is part of the initial backend foundation unless specifically required by a later phase.

## 13. Credits Boundary

Credits will eventually own:

- credit allowances
- credit usage
- outstanding balances
- repayments
- due dates
- credit status

Customers cannot automatically use credit. They require an approved credit allowance before credit can be used. This is a future backend boundary and must not be described as implemented.

## 14. Expenses Boundary

Expenses will own:

- business expenses
- expense categories
- expense records

This boundary is planned and not implemented in the repository.

## 15. Requests Boundary

Requests will own:

- product/customer requests
- request status

This boundary is planned and not implemented in the repository.

## 16. Reports Boundary

Reports must derive from source transactional data.

Examples:

- Sales reports → sales data
- Profit reports → sales + product cost + expenses
- Expense reports → expense records
- Credit reports → credit transactions
- Inventory reports → inventory records

Reports should not create duplicate report tables simply to store calculated totals. Report data should be derived from original transactional data.

## 17. Activity Logs

Status: PLANNED

Important business and financial actions should eventually be auditable. Examples include:

- sale created
- payment recorded
- credit granted
- credit payment made
- expense recorded
- stock adjusted
- product price changed

This log capability is not currently proven to exist in the repository and should remain planned unless later implementation is verified.

## 18. Notifications

Status: PLANNED

Notifications are planned as a backend area for user or customer alerts and message workflows. No verified implementation was found in the repository for this document.

## 19. Migration Safety

Migration safety rules are mandatory for every backend phase:

- Never drop the database to solve migration issues.
- Never casually delete migrations.
- Never fake migrations without understanding the migration state.
- Inspect migration dependencies before changing them.
- Run makemigrations before migrate.
- Run Django checks.
- Run relevant tests after model changes.
- Preserve existing data wherever possible.
- Resolve migration conflicts explicitly and carefully.

## 20. Testing Requirements

For each backend phase attempt, the relevant checks should include:

- python manage.py check
- python manage.py test <relevant_app>
- python manage.py makemigrations
- python manage.py migrate
- git diff --check
- git status

Tests should cover important business rules and migration safety. The repository already contains Product model tests for product uniqueness, price history, and validation, which confirm a working style for backend validation checks.

## 21. Backend Development Roadmap

The verified and planned backend roadmap is:

1. Accounts Foundation — COMPLETE
2. Products Foundation — COMPLETE
3. Inventory Foundation — NEXT
4. Sales/POS — PLANNED
5. Orders — PLANNED
6. Payments — PLANNED
7. Credits — PLANNED
8. Expenses — PLANNED
9. Requests — PLANNED
10. Activity Logs / Notifications — PLANNED
11. Reports — PLANNED
12. Customer Backend Integration — PLANNED

Only a phase that is verified in the repository should be marked COMPLETE.

## 22. Phase Rules

Every backend phase must:

- have a clear scope
- inspect existing code first
- avoid recreating existing files or structures
- avoid changing completed modules unnecessarily
- avoid implementing future phases early
- preserve migrations
- preserve existing data
- run tests
- run Django checks
- verify the git scope before committing

This reduces the risk of mixing backend work with unrelated frontend work or partially completed modules.

## 23. Current Repository State

This repository currently contains mixed or uncommitted work that must be isolated before backend phases are committed individually.

The current working tree confirms uncommitted changes in:

- apps/accounts
- apps/products
- config/settings.py
- config/urls.py
- apps/preview
- docs/MADAM_HY_BACKEND.md
- templates/preview

This means the working tree is not clean at the moment. Backend work must be isolated and reviewed before committing so that completed modules are not mixed with unfinished or unrelated changes.

This document records only what is supported by the repository state and does not claim broader implementation that is not present.

## 24. Summary

The current verified backend foundation is Accounts plus Products. Inventory is the next phase, followed by Sales/POS, Orders, Payments, Credits, Expenses, Requests, Activity Logs, Notifications, Reports, and Customer Backend Integration. The repository confirms the product boundary and the separation between product catalog data and inventory stock ownership.

The backend should continue in that order, with each phase scoped and verified before moving to the next one.
