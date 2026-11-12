# Payments Module

Status: **PARTIAL / SAFE FOUNDATION COMPLETE**

## Implemented
- Payment model
- Methods: CASH, BANK_TRANSFER, CARD, CREDIT
- Statuses: PENDING, COMPLETED, FAILED, REFUNDED
- Sale or Order relationship
- Customer/cashier references
- Transaction reference/metadata
- Validation
- Exactly-one-transaction database constraint
- Historical deletion protection
- Model tests
- Minimal HTTP API: list/create/detail
- PK-based customer and staff access checks
- Basic JSON response contract for Payments records
- Centralized `PaymentService` for validation, creation, method normalization, and transaction-safe payment creation
- Read-only `PaymentService.get_transaction_balance(...)` for Order/Sale payment aggregation
- Optional unique `Payment.idempotency_key` for safe creation retries
- `PaymentService.confirm_payment(...)` for the single `PENDING` → `COMPLETED` transition
- ActivityLog audit record for confirmation actor and timestamp
- Read-only `ReconciliationService` for evaluating Order/Sale balances, counts, and inconsistency findings
- Read-only Management Reconciliation HTTP endpoints: `GET /payments/reconciliation/order/<order_id>/` and `GET /payments/reconciliation/sale/<sale_id>/`
- Reconciliation Phase 2 Management Endpoints:
  - `GET /payments/reconcile/sale/<uuid:sale_id>/` (and `<str:sale_id>/`)
  - `GET /payments/reconcile/order/<uuid:order_id>/` (and `<str:order_id>/`)
  - `GET /payments/reconcile/overview/` (bulk reconciliation overview with summary totals, classification counts, and filtering)
- Reconciliation classification engine: `UNPAID`, `PARTIALLY_PAID`, `FULLY_PAID`, `OVERPAID`
- Strict `OWNER` / `MANAGER` authorization for all reconciliation endpoints (403 for `CUSTOMER`, `CASHIER`, `STAFF`; 401 for unauthenticated)
- Audit logging via `apps.activity_logs.services.log_activity` (`ActivityLog.ActionType.VIEWED`) for management reconciliation report access
- Strict read-only guarantees verified across `Payment`, `Sale`, `Order`, `InventoryItem`, and `CreditAccount` / `CreditTransaction`
- Payment Verification Layer (Phase 3):
  - Extensible provider-neutral interface: `BasePaymentVerifier`, `PaymentVerificationResult`, and `PaymentVerificationStatus` (`VERIFIED`, `FAILED`, `PENDING`, `UNKNOWN`, `MISMATCH`)
  - Standardized verification result schema (`to_dict()`) capturing status, verified amount, provider reference, discrepancy detection, timestamp, and metadata
  - Default `MockPaymentVerifier` and `InternalPaymentVerifier` validating reference structures, positive amounts, expected amounts/references, and currency without external network calls
  - `PaymentVerificationService` registry supporting custom verifier registration and execution
  - Convenience methods `verify_payment_transaction(payment, ...)` and `PaymentService.verify_payment(...)`
  - Management verification endpoint: `POST /payments/<int_uuid_or_str:id>/verify/`
  - Strict role-based access control: `OWNER` and `MANAGER` permitted; `CASHIER`, `STAFF`, and `CUSTOMER` denied with 403 Forbidden; unauthenticated denied with 401
  - Audit logging via `log_activity` (`ActivityLog.ActionType.VIEWED`) for each verification action
  - Guaranteed read-only execution preserving underlying orders, sales, inventory, credits, and payment statuses
  - Comprehensive unit and integration test coverage (96 passing tests in `apps.payments.tests`)

## Current Scope
The current, safe backend slice is limited to payment record lifecycle reads and creation as a standalone API contract, with a central service boundary for validation and compatibility handling. It does not update Orders or Sales state, does not trigger inventory changes, and does not integrate external payment providers.

Payment creation accepts existing Sale and Order records through the same service boundary. The linked transaction must already exist and the customer must match when provided. This is a record-only integration: it does not change Sale or Order status, does not deduct inventory, does not create a Sale, and does not modify the Sales lifecycle.

The service can calculate a selected Order or Sale balance from related Payment records. It returns the transaction total, amounts by current Payment status, collected `COMPLETED` amount, outstanding amount, and overpaid amount using Decimal arithmetic. This calculation is read-only and does not update any transaction or payment fields.

Payment creation accepts an optional `X-Idempotency-Key` request header. The key is trimmed, limited to 120 characters, and stored uniquely. A retry with the same key and equivalent payment data returns the original Payment. Reuse with different transaction, customer/cashier, amount, method, status, transaction reference, metadata, or notes is rejected. Requests without the header preserve the existing `payment_reference` behavior and do not gain idempotent retry semantics.

Payment confirmation is available at `POST /payments/<id>/confirm/` to `OWNER` and `MANAGER` users only. It locks the Payment and permits only `PENDING` → `COMPLETED`. Repeating confirmation for an already completed Payment returns the existing state without creating a duplicate audit event. The existing ActivityLog records the confirming actor, timestamp, related Payment, and old/new statuses.

The creation service rejects `COMPLETED` status by default. An explicitly trusted internal caller may opt in with `allow_completed=True`; the HTTP creation API never exposes that opt-in and cannot bypass confirmation.

Reconciliation endpoints at `/payments/reconcile/order/<order_id>/`, `/payments/reconcile/sale/<sale_id>/`, and `/payments/reconcile/overview/` (as well as legacy `/payments/reconciliation/...`) are restricted to `OWNER` and `MANAGER` roles. They evaluate the transaction's financial status in a strictly read-only manner, producing exact 2-decimal string monetary totals, payment status distributions, overall status classification (`UNPAID`, `PARTIALLY_PAID`, `FULLY_PAID`, `OVERPAID`), and anomaly findings (such as payments exceeding total, customer mismatches, duplicate gateway references, or method discrepancies) without modifying any database records. Successful management accesses are recorded in `ActivityLog` via `log_activity`.

Payment verification endpoint at `POST /payments/<id>/verify/` provides provider-neutral validation against mock/internal provider rules or external providers, checking amounts, reference validity, and metadata discrepancies in a strictly non-destructive manner. Successful verifications are audited via `log_activity`.

## Missing
- Frontend API integration and reconciliation dashboard UI
- External provider integration (e.g. Paystack Phase 4) and webhook handlers
- Reconciliation resolution workflows (taking action on detected discrepancies)
- Refund workflows

## Important Inconsistency
Payments uses `BANK_TRANSFER`.
Orders and Sales currently use `TRANSFER`.

This remains a deliberate compatibility concern that should be handled as part of a future payment integration pass rather than by broad, uncontrolled schema churn.

## Multi-Gateway & POS Terminal Architecture

### 1. Paystack Verification Layer
- **Role**: Online portal checkout, customer credit repayments, dynamic web QR payments.
- **Base URL**: `https://api.paystack.co`
- **Verification Endpoint**: `GET /transaction/verify/{reference}`
- **Security**: Backend `PAYSTACK_SECRET_KEY` only; validates `HMAC-SHA512` webhooks.

### 2. Moniepoint POS Terminal Integration
- **Role**: In-store counter card swipes, physical POS terminal transactions, counter transfers.
- **Key Parameters**: POS RRN (Retrieval Reference Number), Terminal Serial ID, Session Reference.
- **Verification Method**: Moniepoint Transaction Query API matching swiped terminal amounts against shop register sale items.

### 3. In-Store Dynamic QR Code Payments
- **Mechanism**: Dynamic generation of transaction-specific QR codes on POS receipt/screen.
- **Payload**: Pre-calculated amount, shop merchant reference, and dynamic Paystack/Moniepoint checkout URI.

## Current Task Status
Payment Reconciliation Phase 3 (Provider-Neutral Verification Layer) is complete. Extensible verification service, standardized results, mock/internal verifiers, role-gated management verification endpoint (`POST /payments/<id>/verify/`), audit logging, and read-only preservation are fully implemented and verified with tests (96 passing tests). External provider integration (Phase 4 / Paystack), refunds, and frontend UI remain future work.

