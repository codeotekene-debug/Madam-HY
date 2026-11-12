# Activity Logs Module

Status: **COMPLETE**

## Architecture & Responsibilities
The Activity Logs module provides an immutable, regulatory-compliant audit trail recording all significant business events, financial state transitions, status updates, user management actions, and security operations across MADAM HY. Activity log entries are strictly read-only and preserved for historical verification.

## Implemented Components
1. **Model & Immutability Enforcement (`apps.activity_logs.models`)**:
   - `ActivityLog`: Stores `actor` FK (User or null for automated system actions), `action_type` (`CREATED`, `UPDATED`, `DELETED`, `VIEWED`, `APPROVED`, `REJECTED`, `PAYMENT`, `INVENTORY`, `SYSTEM`), `action_label`, `description`, generic relation (`content_type`, `object_id`), structured `metadata` JSON, and timestamps.
   - `ActivityLogQuerySet`: Queryset helpers `.for_actor()`, `.for_action()`, and `.latest()`, plugged into `objects = ActivityLogQuerySet.as_manager()`.
   - Strict Immutability Guards:
     - `clean()`: Prevents any in-place mutation of existing records (`ValidationError` if mutable fields are modified).
     - `delete()`: Overridden to raise `ValidationError`, completely blocking manual or programmatic record deletion.
   - Helper properties: `ip_address`, `user_agent`, `changes_diff` (extracting before/after field diffs).

2. **Service Layer (`apps.activity_logs.services.ActivityLogService`)**:
   - `ActivityLogService.log_activity`: Records audit entries with optional request telemetry (auto-extracting client IP and User-Agent).
   - `ActivityLogService.normalize_action_type`: Canonicalizes action aliases (`CREATE`, `UPDATE`, `DELETE`, `APPROVE`, `APPROVAL`, `REJECT`, `REJECTION`, `PAY`, `STOCK`, `LOGIN`, etc.).
   - `ActivityLogService.get_activity_logs`: Retrieves logs ordered newest-first with multi-criteria filtering:
     - Action type (`action`)
     - Actor (`actor_id` by ID or username)
     - Entity model (`entity`)
     - Date range (`start_date`, `end_date`)
     - Keyword search (`search` / `q`) across description, label, actor, and JSON metadata.
   - `ActivityLogService.get_activity_metrics`: Summary counts of total events, today's events, 24h activity, action breakdown, top actors, and tracked entities.
   - `ActivityLogService.serialize_activity_log`: Formats audit records for JSON API consumption.
   - Preserved backward-compatible standalone functions: `log_activity` and `log_model_activity`.

3. **HTTP Views & Endpoints (`apps.activity_logs.views`, `apps.activity_logs.urls`)**:
   - `GET /activity-logs/` & `/activity-logs/list/` (`activity_logs:list`): Paginated audit log queue with comprehensive query filters; dual HTML rendering (`templates/activity_logs/activity_logs.html`) and JSON payload (`?format=json` or Accept header).
   - `GET /activity-logs/<int:id>/` (`activity_logs:detail`): Detailed log entry inspection with before/after state diff table, formatted JSON metadata viewer, and client telemetry.
   - `GET /activity-logs/metrics/` (`activity_logs:metrics`): Summary statistics endpoint for management dashboards.
   - `/logs/` route configured with permanent redirect to `/activity-logs/`.
   - Security & RBAC: Strictly restricted to `OWNER` and `MANAGER` roles. Non-management roles (`CASHIER`, `STAFF`, `CUSTOMER`) are rejected with `403 Forbidden`. Unauthenticated requests receive 401 Unauthorized for JSON or redirect to login for HTML.
   - Method guards: Non-GET requests (`POST`, `PUT`, `PATCH`, `DELETE`) return `405 Method Not Allowed`.

4. **UI & Templates Integration**:
   - `templates/activity_logs/activity_logs.html`: Audit trail dashboard with summary cards, toolbar filters, action badges, actor attribution, entity tags, IP display, and pagination.
   - `templates/activity_logs/log_detail.html`: Individual record inspector with diff table, metadata viewer, and telemetry attribution.
   - `templates/base.html`: Sidebar navigation link for `OWNER` and `MANAGER` roles under Analytics.
   - `static/css/pages/activity_logs/activity_logs.css`: Styled responsive stylesheet matching MADAM HY design tokens.

5. **Test Coverage (`apps/activity_logs/tests.py`)**:
   - 20 tests passing: model constraints, ordering, immutability (delete and mutation rejection), telemetry extraction, service filtering (action, actor, entity, search), metrics computation, RBAC role checks, HTTP method restrictions (405), HTML template rendering, and JSON API responses.
