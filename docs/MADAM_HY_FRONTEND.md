# MADAM HY Frontend Specification

## Project

MADAM HY is a shop management and customer shopping platform.

The system serves:

1. Physical shop operations
2. Online customers
3. Product requests
4. Business management
5. Business analytics


# Frontend Architecture

The frontend is organized into:

templates/
static/css/
static/js/


## Templates

Pages are organized by application domain.

Existing template directories include:

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


# CSS Architecture

Core styles:

- variables.css
- reset.css
- typography.css
- navbar.css
- forms.css
- modals.css
- tables.css
- responsive.css

Page-specific styles belong in the corresponding page CSS directory.


# JavaScript Architecture

Page JavaScript:

static/js/pages/

AJAX JavaScript:

static/js/ajax/

Keep page interaction logic separate from server communication.


# Design

Brand:

MADAM HY

Primary visual preference:

GREEN

Design characteristics:

- clean
- modern
- professional
- simple
- responsive
- retail-focused


# Responsive

Every page must support:

- desktop
- tablet
- mobile


# Roles

OWNER
MANAGER
CASHIER
STAFF
CUSTOMER


# Development Phases

## Phase 1

Complete frontend pages.

HTML
CSS
JavaScript
Responsive design


## Phase 2

Connect Django.

URLs
Views
Models
Forms
Database


## Phase 3

AJAX/API.

Page JS
→ AJAX
→ Django
→ Database


## Phase 4

Security.

Authentication
Role permissions
Object-level permissions
Server-side authorization


## Phase 5

Business functionality.

Products
Inventory
Sales
Orders
Payments
Credits
Expenses
Reports
Growth
Notifications
Product requests


# Important

Do not create a new architecture.

Use the existing repository structure.

Inspect existing files before modifying them.