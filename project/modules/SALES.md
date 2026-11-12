# Sales Module

Status: **SUBSTANTIALLY COMPLETE / ACTIVE**

## Implemented
- Sale and SaleItem models
- Sale creation
- Sale detail/history
- Payment validation during completion
- Cash overpayment/change
- Transfer/card exact payment validation
- Credit sale handling
- Inventory deduction during completion
- Sales reporting
- Customer access controls
- Extensive tests

## Dependencies
Accounts, Products, Inventory, Orders, Payments.

## Critical Rule
Do not break sale completion's inventory and payment validation transaction behavior.

## Safe Payment & Credit Integration
- Payments may be recorded against an existing Sale through the centralized `PaymentService` without changing the Sale lifecycle (record-only linkage).
- Credit sales (`payment_method='CREDIT'`) are fully enforced within `Sale.complete_sale()`:
  - Pre-validates that the customer holds an approved, active `CreditAccount` with sufficient available credit (`CreditService.validate_credit_eligibility`).
  - Deducts inventory atomically.
  - Atomically records the `CreditTransaction` (`CREDIT_PURCHASE`) and updates the `CreditAccount` balance using row-level locking (`CreditService.process_credit_sale`).
  - Entire operation executes in a single database transaction (`@transaction.atomic`), ensuring full rollback if inventory or credit operations fail.

## Next
Final UI/API reconciliation and customer Order credit workflow, while preserving the existing sale completion, payment validation, and credit ledger transaction rules.
