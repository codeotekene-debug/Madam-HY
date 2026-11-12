# Requests Module

Status: **COMPLETE / ACTIVE**

## Purpose
Manages customer-facing inquiries, support tickets, and product requests independently from orders, sales, payments, credits, and inventory. Provides a staff/management triage queue, status transition lifecycle, and staff assignment.

## Implemented Architecture & Features

### 1. Model & Data Integrity (`apps.requests.models.Request`)
- Fields: `uuid`, `request_number` (unique), `customer`, `request_type`, `title`, `description`, `status`, `priority`, `product`, `quantity`, `assigned_to`, `resolution`, `notes`, `attachment`, `created_at`, `updated_at`, `resolved_at`.
- Statuses: `PENDING`, `REVIEWING`, `APPROVED`, `PROCESSING`, `COMPLETED`, `REJECTED`, `CANCELLED`.
- Priorities: `LOW`, `NORMAL`, `HIGH`, `URGENT`.
- Types: `PRODUCT`, `GENERAL`, `SUPPORT`, `OTHER`.
- Strict validation rules:
  - Customer must have `role == 'CUSTOMER'`.
  - Assigned staff must have an authorized staff role (`OWNER`, `MANAGER`, `CASHIER`, `STAFF`) and cannot be a customer.
  - Completed requests must include a resolution response.
  - Resolved timestamp recorded on completion, rejection, or cancellation.
  - Historical protection: Completed/resolved records cannot be casually deleted.

### 2. Service Layer (`apps.requests.services.RequestService`)
- Centralized business logic:
  - `create_request`: Customer request submission, input normalization, audit logging, and staff in-app notification.
  - `update_status`: Validates staff/manager permissions, enforces lifecycle transition rules, records resolution, logs audit events, and triggers in-app notification to the customer.
  - `assign_request`: Assigns or reassigns staff handler, transitions status from PENDING to REVIEWING, logs audit events, and notifies assignee.
  - `get_summary_metrics`: Computes total, pending, in-review, approved, completed, rejected, and urgent ticket counts.

### 3. Forms Layer (`apps.requests.forms`)
- `CustomerRequestCreateForm`: Clean form validation for customer-facing submissions.
- `StaffRequestCreateForm`: Allows staff to submit tickets on behalf of customers.
- `RequestStatusUpdateForm`: Handles status updates and resolution notes.
- `RequestAssignForm`: Handles handler assignment.

### 4. HTTP Endpoints & Views (`apps.requests.views`)
- **Staff/Management Request Queue**: `GET /requests/` (paginated, keyword search, filters for status, priority, type, staff assignee, and date range).
- **Customer Request List**: `GET /requests/my/` and `/customer/requests/` (strictly isolated to the authenticated customer).
- **Request Submission**: `GET`/`POST /requests/create/` (supports customer submission and staff creation).
- **Request Detail**: `GET /requests/<uuid:id>/` and `GET /requests/<str:id>/` (supports UUID, request_number, and integer PK; strictly isolates customer tickets with 403 Forbidden on cross-customer access).
- **Status Lifecycle Transition**: `POST /requests/<uuid:id>/status/` (Staff/Management only).
- **Staff Assignment**: `POST /requests/<uuid:id>/assign/` (Staff/Management only).
- **Dual Response Support**: HTML template rendering and JSON API (`?format=json` or `Accept: application/json`).

### 5. Security & Isolation
- Unauthenticated requests denied with 401 (JSON) or redirected to login (HTML).
- Strict object-level customer isolation: Customers attempting to inspect tickets belonging to other customers receive 403 Forbidden.
- Role-based permissions: Customers cannot assign staff or transition ticket statuses (403 Forbidden).

### 6. Audit Logging & In-App Notifications
- Every request creation, status transition, and assignment is recorded in `ActivityLog`.
- In-app notifications generated for customers on status updates and for staff on new urgent tickets or assignment via `apps.notifications.services.create_notification`.

## Verification & Tests
- 45 tests in `apps/requests/tests.py` passing:
  - `RequestModelTests` (22 model integrity & architectural boundary tests)
  - `RequestServiceTests` (Service creation, validation, lifecycle, assignment, metrics)
  - `RequestCustomerWorkflowTests` (Customer creation, own list, own detail, strict cross-customer 403 isolation, template rendering)
  - `RequestManagementWorkflowTests` (Queue listing, filtering, search, status transitions via UUID/ID, assignment, detail view)
  - `RequestRBACAndSecurityTests` (Unauthenticated 401s, customer 403 on status/assignment)
  - `RequestValidationTests` (Empty title/description, invalid quantity, missing resolution, 404s)
  - `RequestAuditAndNotificationTests` (ActivityLog audit verification, customer in-app notifications, staff assignment notifications)
