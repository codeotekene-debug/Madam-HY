# Delivery Module

Status: **RIDER AND MANAGEMENT UI IMPLEMENTED; OPERATIONAL FLOW VALIDATION IN PROGRESS**

## Current Architecture

- `apps.delivery` is registered in Django and its URL configuration is included at the project root.
- `accounts.User` has the dedicated `RIDER` role. Public registration still creates `CUSTOMER` accounts only, and successful rider login resolves to `/rider/`.
- Authorized management provisions rider accounts with an initial password validated by Django's configured password validators; there is no shared default rider password.
- `RiderProfile` stores rider vehicle and availability fields and is one-to-one with a rider account.
- `DeliveryZone`, `Delivery`, `DeliveryStatusHistory`, and `DeliverySetting` provide zone, delivery, status, and configuration records.
- `DeliveryAssignment` records each assignment attempt with the delivery, rider, assigning manager, outcome, timestamps, and reason. Assignment history protects its delivery and rider references against deletion.
- Order already has delivery-zone and delivery-fee fields. Delivery fee calculation and checkout behavior still need end-to-end verification.

## Integration Boundaries

- Delivery progress is a separate lifecycle from `Order` and `Sale` status.
- Rider actions must not call Order-to-Sale conversion or change payment/inventory records.
- Public registration must never create RIDER accounts. Authorized management provisions riders.
- Riders may access only deliveries currently assigned to them; management access remains owner, manager, and authorized staff.

## Audit Findings / Remaining Work

- Checkout zone selection, authoritative fee calculation, and order total snapshot still need end-to-end integration.
- Delivery creation currently has no payment-eligibility gate. Define and enforce the approved prepaid, credit, and any pay-on-delivery rules before dispatch is enabled.
- The complete delivery service, OTP, notifications, payment policy, tracking, and management workflow still needs end-to-end acceptance.

## Current Implementation Update (2026-11-04)

- Responsive rider pages now cover overview, new jobs, job details, active delivery, history, profile, and notifications. Management pages cover dashboard, queues, detail, rider management, zones, settings, and reports.
- Assignment history is updated for assign/reassign, accept/reject, completion, failure, return, and cancellation. OTP comparison uses constant-time digest comparison; failed attempts persist.
- Customer order detail displays delivery status history and active rider contact.
- Checkout-to-delivery integration still needs zone selection, authoritative fee calculation, and order total snapshot verification. Delivery creation now preserves the order fee rather than silently substituting the current zone price.
- Payment eligibility before dispatch still needs an explicit policy and implementation. Delivery milestones remain separate from order, sale, payment, and inventory completion.
- Full browser/accessibility acceptance and the complete project test suite remain outstanding.
