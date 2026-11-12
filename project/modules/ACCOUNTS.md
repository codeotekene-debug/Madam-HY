# Accounts Module

Status: **COMPLETE / ACTIVE**

## Architecture & Responsibilities
The Accounts module handles user authentication, registration, role-based authorization, profile management, and persistent communication/delivery preferences for MADAM HY customers, staff, and management.

## Implemented Components
1. **Custom User Model & Preferences (`apps.accounts.models.User`)**:
   - Authentication via email (`USERNAME_FIELD = 'email'`) or username.
   - Role-based authorization (`ROLE_CHOICES`: OWNER, MANAGER, CASHIER, STAFF, CUSTOMER, RIDER).
   - Profile information (`phone_number`, `first_name`, `last_name`).
   - Communication & notification delivery preference flags:
     - `order_notifications` (Boolean, default: True)
     - `payment_notifications` (Boolean, default: True)
     - `request_notifications` (Boolean, default: True)
     - `promotion_notifications` (Boolean, default: False)
   - Experience & delivery preferences (`preferences` JSONField, default: dict) storing language, currency, marketing opt-in, and preferred delivery method.
   - Helper methods:
     - `get_notification_preferences()`: Returns dictionary of notification flags and aliases.
     - `get_preferences()`: Returns normalized structure (`notifications`, `preferences`, `delivery`) matching frontend and API schemas.

2. **Customer Profile (`apps.accounts.models.CustomerProfile`)**:
   - 1-to-1 extension for `CUSTOMER` role users.
   - Contact details (`address`, `city`, `state`, `postal_code`), `preferred_payment_method`, and internal notes.

3. **HTTP Views & API Endpoints (`apps.accounts.views`, `apps.accounts.urls`)**:
   - `POST /accounts/login/` (`accounts:login`): Authentication with email or username.
   - `POST /accounts/logout/` (`accounts:logout`): Session termination.
   - `POST /accounts/register/` (`accounts:register`): Customer registration.
   - `GET /accounts/profile/` (`accounts:profile`): Authenticated user details.
   - `POST /accounts/change-password/` (`accounts:change_password`): Secure password update.
   - `GET /customer/settings/` & `/accounts/settings/` (`accounts:settings`):
     - Renders `templates/customer/settings.html` with current user preferences.
     - Dual response: returns JSON if requested (`?format=json` or Accept header).
     - Requires authentication (`@login_required` redirect or 401 JSON).
   - `GET`/`POST /accounts/settings/notifications/` & `/api/customer/preferences/` (`accounts:settings_notifications`, `accounts:preferences`):
     - `GET`: Returns current preferences for authenticated user.
     - `POST`: Validates and updates notification flags and preferences JSON with strict input validation.
     - Customer isolation: Rejects cross-user modifications with 403 Forbidden.
     - Audit logging: Records preference modifications in `ActivityLog` with before/after state diff.

4. **UI & Template Integration**:
   - `templates/customer/settings.html`: Server-rendered checkbox and select states, initial JSON script embedding, CSRF token, and alert banners.
   - `static/js/pages/customer/settings.js`: Interactive preferences toggle and save workflow with live AJAX submission, error handling, and default resetting.
   - `templates/base.html`: Navigation links to Settings for Customer and Administration sections.
   - `templates/customer/dashboard.html`: Account settings quick action link to `/customer/settings/`.

5. **Test Coverage (`apps/accounts/tests.py`)**:
   - `AuthApiTests`: Login, registration role restrictions, password changing, profile retrieval.
   - `CustomerNotificationPreferencesTests`:
     - Default model preference flags and helpers.
     - Settings view authentication and dual HTML/JSON rendering.
     - Preferences API GET and POST updates (flat and nested payloads).
     - Payload validation (rejects invalid boolean types/strings and malformed JSON with 400).
     - Customer isolation enforcement (cross-user retrieval and mutation blocked with 403).
     - Manager/owner inspection of customer preferences.
     - Audit logging verification on preference changes.

6. **Rider Account Boundary**:
   - `RIDER` is a dedicated role and successful rider login redirects to the rider portal.
   - Public registration remains restricted to `CUSTOMER`; rider accounts are provisioned by authorized management through the delivery module.
   - Rider authorization is enforced by delivery-specific views and decorators, not by broad management permissions.
