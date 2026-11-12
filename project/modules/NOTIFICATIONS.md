# Notifications Module

Status: **COMPLETE**

## Architecture & Responsibilities
The Notifications module provides a lightweight, recipient-isolated in-app notification center that tracks real-time business and system events (orders, payments, credit changes, requests, low stock inventory, expenses, and system alerts). It operates independently from transactional core logic and ensures that read state updates do not mutate transactional data.

## Implemented Components
1. **Model & QuerySet (`apps.notifications.models`)**:
   - `Notification`: Stores recipient FK, `notification_type` (`ORDER`, `PAYMENT`, `CREDIT`, `REQUEST`, `INVENTORY`, `EXPENSE`, `SYSTEM`), `priority` (`LOW`, `NORMAL`, `HIGH`, `URGENT`), `title`, `message`, `is_read`, `read_at`, generic foreign key (`content_type`, `object_id`), and optional `action_url`.
   - `NotificationQuerySet`: Provides custom queryset helpers `.unread()` and `.read()`, configured as model manager.
   - Database indexes on `(recipient, -created_at)`, `(recipient, is_read, -created_at)`, `(notification_type, -created_at)`, `(priority, -created_at)`, and `(is_read, -created_at)`.
   - Methods: `mark_as_read()` and `mark_as_unread()`.

2. **Service Layer (`apps.notifications.services.NotificationService`)**:
   - `NotificationService.create_notification`: Creates validated notifications with optional audit logging.
   - `NotificationService.get_user_notifications`: Retrieves notifications isolated to a single recipient, with filters for read status (`is_read`), type (`notification_type`), priority, and keyword search (`search`).
   - `NotificationService.get_unread_count`: Fast query for active unread count.
   - `NotificationService.get_notification_metrics`: Returns dictionary containing `total`, `unread`, `read`, and `urgent_unread` counts.
   - `NotificationService.mark_as_read`: Updates notification to read; strictly raises `PermissionDenied` on cross-user mutation attempts.
   - `NotificationService.mark_as_unread`: Reverts read status with user isolation.
   - `NotificationService.mark_all_as_read`: Atomically updates all unread notifications for the user.
   - `NotificationService.serialize_notification`: Serializes notification records for JSON APIs.
   - Backward-compatible standalone functions: `create_notification`, `mark_all_notifications_as_read`, `unread_notifications_count`.

3. **HTTP Views & Endpoints (`apps.notifications.views`, `apps.notifications.urls`)**:
   - `GET /notifications/` (`notifications:inbox`, `notifications:list`): Paginated user inbox supporting filters (`is_read`, `type`, `priority`, `q`). Renders HTML template or returns JSON based on content negotiation (`?format=json` or Accept header).
   - `GET /notifications/unread-count/` (`notifications:unread_count`): Lightweight endpoint returning `{ "unread_count": <int> }` for navbar badge updates. Returns 401 if unauthenticated.
   - `POST /notifications/<int:id>/read/` & `POST /notifications/<str:id>/read/` (`notifications:mark_read`, `notifications:mark_read_str`): Marks notification as read. Enforces strict user isolation (returns 403 Forbidden for another user's notification, 404 for missing notification, 400 for invalid ID format).
   - `POST /notifications/<int:id>/unread/` & `POST /notifications/<str:id>/unread/` (`notifications:mark_unread`, `notifications:mark_unread_str`): Reverts single notification to unread.
   - `POST /notifications/read-all/` (`notifications:mark_all_read`): Bulk-marks all unread notifications for the authenticated user.
   - Unauthenticated access handling: returns 401 Unauthorized for JSON requests and redirects to login for HTML requests.

4. **Templates & Frontend Integration**:
   - `templates/notifications/notifications.html`: Complete UI with summary cards (Total, Unread, Read, Urgent), toolbar filters, notification cards with category icons/priority pills, pagination, and empty state.
   - `templates/base.html`: Topbar bell (`#notificationBell`) linking to `/notifications/` with dynamic badge (`#notificationBadge`).
   - `static/css/pages/notifications/notifications.css`: Styled design adhering to MADAM HY design tokens.
   - `static/js/pages/notifications/notifications.js`: Asynchronous AJAX mark-as-read/unread toggling with live counter updates.
   - `static/js/core/notifications.js`: Global `NotificationsManager` handling initial unread count fetch, tab visibility change detection, periodic polling, and badge updates.

5. **Test Coverage (`apps/notifications/tests.py`)**:
   - 42 tests passing: model constraints, ordering, non-destructive behavior across all core models, service filtering and metrics, strict user isolation, HTTP views rendering, JSON API content negotiation, unread counter accuracy, mark-read/mark-unread endpoints, and mark-all-read bulk mutation.
