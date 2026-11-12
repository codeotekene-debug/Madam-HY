# Smart Shop — Current Decisions & Development Constraints

**Updated:** 2026-09-04

This file records decisions that must survive agent/model handoffs. It is a decision log, not a duplicate task tracker.

## 1. Product AI Agent Is Future Work

The Smart Shop product AI agent is explicitly **OUT OF CURRENT SCOPE**.

Do not implement, design, optimize, or prepare LangChain, LangGraph, OpenAI agent functionality, Tavily, agent memory, AI endpoints, or AI workflows until the main Smart Shop application is completed, tested, secured, and production-ready.

Current work is only the business application.

## 2. Source of Truth

For implementation decisions, use this authority order:

1. Actual source code
2. Tests and their behavior
3. Database models/migrations
4. Current working-tree state
5. `project/STATUS.md`
6. `project/ROADMAP.md`
7. `project/PROJECT.md`
8. Architecture/module documentation
9. Older Git history

If documentation conflicts with source/tests, report the conflict and update the documentation when appropriate. Do not silently implement from stale documentation.

## 3. Working Tree Safety

The current project may contain work newer than Git HEAD. Never reset, revert, checkout, clean, stash, or discard existing changes without explicit permission. Do not commit unless explicitly instructed.

## 4. Context/Usage Optimization

Reading files consumes model/agent context and usage. Future agents must not reread the whole repository for every task.

For each task:
- Start with `project/STATUS.md`.
- Read only the relevant module/architecture documents.
- Read only the source files directly involved in the task.
- Read related tests before changing business logic.
- Expand context only when the code requires it.
- Do not repeatedly reread unchanged files already understood in the current task.
- Use the least expensive capable model; use stronger reasoning for financial, payment, inventory, authorization, concurrency, database, or architecture changes.

Every completed task should leave a compact handoff in `project/STATUS.md` containing the exact next-task context needed by the next agent.

## 5. Business Integrity Comes Before UI Polish

Development priority is:

1. Business correctness
2. Financial/data integrity
3. Security and authorization
4. Backend/domain integration
5. Frontend integration
6. End-to-end workflows
7. Regression testing
8. Production hardening
9. UI polish/accessibility/device QA

## 6. Orders and Sales Are Different Domains

Orders and POS Sales remain separate concepts. An Order may be converted to a Sale. Creating an Order must not itself deduct inventory.

Do not merge their lifecycles casually.

## 7. Payments Boundary

The Payments service owns payment-record validation, creation, normalization, idempotency, confirmation, and payment aggregation/reconciliation calculations.

Payment confirmation must not automatically mutate Order/Sale lifecycle, inventory, credit balances, or create unrelated notifications unless a separately approved business rule establishes that behavior.

## 8. Credit Must Become a Real Business Workflow

Credit models and services exist, but credit enforcement is not yet consistently integrated into production POS Sales and customer Orders.

The intended next implementation slice is to enforce credit eligibility/available-credit rules for POS credit sales and atomically record the corresponding credit ledger transaction with the sale/inventory operation.

Do not build the entire credit API/UI in the same task. Keep the first integration slice isolated and testable.

## 9. Historical Financial Accuracy

Sale items preserve selling-price/name/SKU snapshots. Historical cost/profit behavior requires deliberate treatment because reporting currently relies on product cost data. Do not silently change costing methodology; establish the intended historical costing rule before changing it.

## 10. Preview Is Not Production

`apps/preview/` and its routes are preview/demo rendering surfaces. The existence of a template or preview route does not mean the corresponding production workflow is implemented.

## 11. Documentation Is Part of Completion

A task is not complete until `project/STATUS.md` records:
- what was completed
- files changed
- tests/checks
- results
- known issues
- next task
- minimum context needed for the next task

Update `project/ROADMAP.md` when the implementation plan changes.
Update stable architecture/product documentation only when the underlying decision is actually established.

## 12. Production Settings Hardening & Security Configuration Baseline

Production deployments must never run with development fallback secrets or wildcard hosts:
- `DEBUG` defaults to `False` in production; evaluated safely via boolean parsing.
- `SECRET_KEY` is strictly required from environment when `DEBUG=False`. Keys shorter than 50 characters, keys with low entropy (< 5 unique characters), default placeholders, or keys starting with `django-insecure-` raise `ImproperlyConfigured`.
- `ALLOWED_HOSTS` requires explicit non-wildcard hostnames when `DEBUG=False`.
- Security headers and secure cookies (`SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS='DENY'`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`, `SECURE_SSL_REDIRECT`) default to secure production values when `DEBUG=False`, while preserving HTTP operation for local development when `DEBUG=True`.
- Production logging uses `logging.handlers.RotatingFileHandler` (10MB limit, 5 backups) and includes `django.security` auditing.
- Database configuration supports `DATABASE_URL` and individual MySQL/Postgres credentials with fallback to SQLite for local development out-of-the-box.
- `python manage.py check --deploy` must pass with zero issues in production configuration.

## 13. Customer Store Campaign Placement & Motion

- Store announcements and promotional scrolling content belong within the customer page content, below the catalog hero, rather than above the shared storefront header.
- Store campaign copy must use configured, verifiable product or store information; do not invent prices, discounts, delivery terms, payment methods, or guarantees.
- Moving campaign content must include a pause control and stop automatically when the user requests reduced motion.


## 14. Rider Access and Delivery Records

- Rider accounts use a dedicated RIDER role and are provisioned by authorized management. Public registration remains limited to CUSTOMER accounts.
- Delivery progress and assignment history are separate from Order and Sale financial lifecycles. Rider delivery actions must not complete a Sale, change payment state, or deduct inventory.
- Each assignment attempt is retained as a DeliveryAssignment record. Historical assignment records protect their delivery and rider references from deletion.


### Delivery dispatch and pricing boundaries (2026-11-04)
- Customer checkout selects an active DeliveryZone; its fee is snapshotted on Order and included in the order total. Later zone price edits must not rewrite historical order fees.
- Delivery dispatch requires a confirmed/prepared order and either confirmed payment, credit-paid status, or eligible cash/pay-on-delivery. Rider delivery completion must not complete the Order/Sale or mutate payment/inventory.
- Confirming a doorstep order creates its Delivery record; pickup orders do not enter rider dispatch.
