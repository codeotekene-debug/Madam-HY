# Backend Architecture

## Framework
Django with function-based views and JSON API-style responses.

## App Boundaries
Each business domain is separated into a Django app.

Core transactional domains:
- Orders
- Sales
- Payments
- Inventory

Supporting domains:
- Accounts
- Products
- Credits
- Expenses
- Reports
- Notifications
- Requests
- Activity Logs
- Delivery

The Delivery app has a separate `RIDER` account role, rider profiles, delivery records, zones, and settings. Its operational views and templates are not yet validated as a complete rider workflow.

## Response Pattern
Orders, Sales, Inventory and Products use helper functions for JSON responses and explicit HTTP status codes.

## Authorization
Authorization is primarily role-based in views. Customer endpoints also filter data by the authenticated customer.

## Transaction Principles
Business-critical operations such as sale completion and order conversion must preserve consistency across related records.

## Payment Service Boundary
The Payments app now includes a focused internal service layer that owns: validation, payment creation, transaction association checks, status normalization, compatibility handling for legacy `TRANSFER` terminology, read-only balance aggregation for an existing Order or Sale, idempotent payment creation, and the locked `PENDING` → `COMPLETED` confirmation transition. Confirmation uses the existing ActivityLog service for actor/timestamp auditability and does not mutate Order or Sale lifecycle fields, inventory, or credit balances.

## Source of Truth
Models and tested backend behavior are authoritative. Frontend previews are not evidence of backend functionality.
