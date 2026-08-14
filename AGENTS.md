# MADAM HY — Codex Project Instructions

## 1. PROJECT OVERVIEW

This is MADAM HY, a Django-based shop management and customer shopping
system for a physical retail business.

The system serves both:

- The physical shop
- Customers who want to shop online or request products that are not
  currently available in the shop

The project uses:

- Python
- Django
- MySQL
- HTML
- CSS
- JavaScript
- AJAX
- Django templates

The frontend is designed for:

- Desktop
- Tablet
- Mobile

The visual identity is based primarily on GREEN because the business
owner prefers green.

Business name:

MADAM HY


--------------------------------------------------
## 2. VERY IMPORTANT — EXISTING ARCHITECTURE
--------------------------------------------------

DO NOT redesign or replace the existing project architecture.

The project already has an established folder and file structure.

Before making changes:

1. Inspect the repository.
2. Inspect the existing templates folder.
3. Inspect the existing static folder.
4. Inspect existing CSS files.
5. Inspect existing JavaScript files.
6. Inspect existing Django apps.
7. Reuse existing files whenever possible.

DO NOT create duplicate files.

DO NOT create a second folder structure.

DO NOT rename existing files unless explicitly instructed.

DO NOT move existing files unless explicitly instructed.

DO NOT replace the existing architecture with a different architecture.

If a file already exists, modify it instead of creating another version.


--------------------------------------------------
## 3. CURRENT DEVELOPMENT PHASE
--------------------------------------------------

The current development phase is:

FRONTEND PAGE DEVELOPMENT.

The immediate goal is to complete the existing pages.

For this phase:

FOCUS ON:

- HTML
- Django templates
- CSS
- responsive design
- page JavaScript
- UI interactions

DO NOT implement the complete backend yet.

DO NOT implement database-dependent functionality yet unless required
for the page structure.

DO NOT build the complete AJAX/API layer yet.

DO NOT create unnecessary Django models.

DO NOT redesign the database architecture during frontend development.


--------------------------------------------------
## 4. FRONTEND ARCHITECTURE
--------------------------------------------------

The project separates frontend responsibilities.

The general architecture is:

HTML
↓
Page CSS
↓
Page JavaScript
↓
AJAX JavaScript
↓
Django backend
↓
Database


### HTML

HTML/Django templates define:

- page structure
- layout
- content areas
- forms
- tables
- buttons
- cards
- modals
- navigation


### PAGE CSS

Page-specific styling belongs in the appropriate page CSS file.

Do not put large amounts of page-specific CSS into the core CSS files.


### CORE CSS

The project already has core CSS files.

Existing core CSS includes:

- variables.css
- reset.css
- typography.css
- navbar.css
- sidebar.css
- forms.css
- modals.css
- tables.css
- components.css
- responsive.css

components.css is intentionally part of the existing MADAM HY design
system. Do not delete it or recreate it.

Do not duplicate styles already handled by:

- forms.css
- modals.css
- tables.css
- navbar.css
- sidebar.css
- components.css
- responsive.css


### PAGE JAVASCRIPT

Page JavaScript handles:

- UI interactions
- dropdowns
- tabs
- filters
- search UI
- modal opening/closing
- client-side calculations
- UI state
- page-specific interactions


### AJAX JAVASCRIPT

AJAX JavaScript is responsible for communication with Django.

Keep AJAX communication separate from general page interaction JavaScript.

Do not put large AJAX requests directly inside page JavaScript when an
AJAX file already exists for that page.


--------------------------------------------------
## 5. EXISTING TEMPLATE STRUCTURE
--------------------------------------------------

The project already contains a template structure.

IMPORTANT:

Inspect the actual repository before modifying it.

The established template organization includes areas for:

- accounts
- dashboard
- products
- inventory
- sales
- orders
- payments
- credits
- expenses
- reports
- requests
- customers
- staff
- notifications
- settings
- customer

There is also:

templates/base.html

Use the existing files.

Do not recreate pages that already exist.


--------------------------------------------------
## 6. EXISTING STATIC STRUCTURE
--------------------------------------------------

The project already contains a structured static directory.

It separates:

- core CSS
- page CSS
- core JavaScript
- page JavaScript
- AJAX JavaScript
- images
- icons

Inspect the existing static directory before creating anything.

Do not create duplicate CSS or JS files.


--------------------------------------------------
## 7. BASE TEMPLATE
--------------------------------------------------

base.html is the common layout for the application.

It should provide the shared application shell.

The shared layout includes:

- MADAM HY branding
- sidebar
- navigation
- topbar
- user information
- notification area
- main content area
- mobile navigation
- shared CSS
- shared JavaScript

Individual pages should extend base.html whenever appropriate.

Do not duplicate the entire application shell in every page.


--------------------------------------------------
## 8. RESPONSIVE DESIGN
--------------------------------------------------

Every page must work on:

- Desktop
- Tablet
- Mobile

Do not design desktop only.

Do not simply shrink the desktop layout.

Mobile layouts should be intentionally designed.

Consider:

- navigation
- sidebar
- cards
- tables
- forms
- buttons
- spacing
- typography
- modals
- filters
- search
- charts
- touch interaction


--------------------------------------------------
## 9. DESIGN SYSTEM
--------------------------------------------------

Use the existing design tokens in:

css/core/variables.css

Do not hard-code colors everywhere.

Use the existing variables for:

- primary green
- darker green
- lighter green
- background
- surface
- text
- muted text
- borders
- shadows
- spacing
- border radius

The visual design should feel:

- professional
- clean
- modern
- trustworthy
- simple
- suitable for a retail business


--------------------------------------------------
## 10. USER ROLES
--------------------------------------------------

The application has different user roles.

Primary roles:

OWNER
MANAGER
CASHIER
STAFF
CUSTOMER

Different roles have different access privileges.

Never assume that every authenticated user can access every page.

The UI should respect the user's role.

The backend will later enforce permissions as the authoritative security
layer.

Frontend hiding is NOT considered security.


--------------------------------------------------
## 11. OWNER
--------------------------------------------------

The OWNER has the highest business-management privileges.

The owner should be able to manage:

- dashboard
- products
- inventory
- sales
- orders
- payments
- customers
- credits
- expenses
- reports
- business growth
- product requests
- staff
- notifications
- settings
- permissions


--------------------------------------------------
## 12. MANAGER
--------------------------------------------------

The MANAGER has business operational privileges according to the
application permission system.

The manager may work with:

- products
- inventory
- sales
- orders
- customers
- credits
- reports

Do not automatically give manager owner-only settings or permissions.


--------------------------------------------------
## 13. CASHIER
--------------------------------------------------

The CASHIER is primarily responsible for shop transactions.

Important functions include:

- POS
- creating sales
- checkout
- accepting payments
- card payments
- transfer payments
- receipts
- customer lookup
- order handling

The cashier should not automatically have access to owner financial
settings or sensitive business-management functions.


--------------------------------------------------
## 14. STAFF
--------------------------------------------------

STAFF permissions depend on their assigned permissions.

Do not assume every staff member has identical access.

Use the application's permission system when it is implemented.


--------------------------------------------------
## 15. CUSTOMER
--------------------------------------------------

Customers have a separate customer-facing experience.

Customers should be able to:

- browse products
- view product details
- add products to cart
- checkout
- view orders
- view order details
- view credit
- view activities
- request products
- manage profile

A customer can request a product that is not currently available in
the shop.

The shop can then help find/source that product from the market.


--------------------------------------------------
## 16. PHYSICAL SHOP PAYMENTS
--------------------------------------------------

The system must support transactions made physically inside the shop.

A customer should not be required to visit the public website just to
pay at the physical shop.

The shop interface/POS must eventually support:

- cash
- bank transfer
- card payment

Payment processing will be connected later.

Do not invent payment provider APIs during the frontend phase.


--------------------------------------------------
## 17. BUSINESS MANAGEMENT
--------------------------------------------------

The system is intended to help the owner understand the business.

The owner dashboard/reports should eventually provide information such
as:

- today's sales
- monthly sales
- profit
- loss
- expenses
- customer credit
- inventory
- low-stock products
- orders
- sales trends
- profit trends
- business growth
- product demand


--------------------------------------------------
## 18. PRODUCT REQUESTS
--------------------------------------------------

Customers can request products that are not currently available.

The request system should eventually allow:

CUSTOMER
→ submit product request

SHOP
→ receive request

OWNER/STAFF
→ review request

SHOP
→ search/source product

SHOP
→ update request status

CUSTOMER
→ see request status


--------------------------------------------------
## 19. PAGE DEVELOPMENT RULE
--------------------------------------------------

When building a page:

1. Inspect the existing HTML file.
2. Inspect its existing CSS file.
3. Inspect its existing JavaScript file.
4. Inspect related core CSS.
5. Reuse existing classes and variables.
6. Complete the page.
7. Make it responsive.
8. Do not duplicate existing components.
9. Do not redesign unrelated pages.
10. Keep changes scoped to the current task.


--------------------------------------------------
## 20. DO NOT CONNECT BACKEND YET
--------------------------------------------------

During the current frontend phase, use realistic placeholder/demo data
when necessary to make the interface visually complete.

Clearly separate placeholder data from real backend data.

Do not create fake database records.

Do not pretend an API exists when it has not been implemented.


--------------------------------------------------
## 21. DO NOT BREAK EXISTING WORK
--------------------------------------------------

Before changing a file:

Inspect it.

Preserve useful existing code.

Do not overwrite working code unnecessarily.

Do not remove existing functionality simply to simplify the code.

If an architectural conflict is discovered:

STOP and explain the conflict before making a large architectural change.


--------------------------------------------------
## 22. CODE QUALITY
--------------------------------------------------

Prefer:

- readable code
- simple code
- semantic HTML
- accessible controls
- reusable styles
- meaningful class names
- maintainable JavaScript
- minimal duplication

Avoid:

- unnecessary frameworks
- unnecessary dependencies
- huge JavaScript files
- inline styles
- inline JavaScript
- duplicated CSS
- magic values
- unnecessary abstractions


--------------------------------------------------
## 23. ACCESSIBILITY
--------------------------------------------------

Use:

- semantic HTML
- labels for form fields
- accessible buttons
- keyboard-friendly controls
- appropriate ARIA attributes when needed
- visible focus states
- readable contrast


--------------------------------------------------
## 24. FRONTEND COMPLETION GOAL
--------------------------------------------------

The goal of this phase is to make all existing pages visually complete
and responsive before connecting the backend.

The pages should look like one consistent application.

Do not make each page look like a separate website.


--------------------------------------------------
## 25. AFTER FRONTEND COMPLETION
--------------------------------------------------

Only after the frontend pages are complete should we proceed to:

1. Django URLs
2. Django views
3. Models
4. Database
5. Forms
6. Authentication
7. Permissions
8. AJAX/API endpoints
9. Payment integration
10. Inventory logic
11. Sales logic
12. Credit system
13. Reports
14. Analytics
15. Notifications
16. Testing


--------------------------------------------------
## 26. IMPORTANT FINAL RULE
--------------------------------------------------

Before every task:

INSPECT FIRST.

Do not assume the repository matches documentation.

The actual files in the repository are the source of truth.

If documentation and the repository disagree:

- inspect the code
- preserve existing working architecture
- report the discrepancy
- do not blindly recreate the documented structure.
