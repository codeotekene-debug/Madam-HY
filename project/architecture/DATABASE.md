# Database Architecture

## Database
MySQL configured through Django settings.

## Core Relationships

User
- has CustomerProfile
- may create/process orders and sales
- may receive notifications
- may record expenses/activity

Product
- belongs to ProductCategory
- has ProductImage records
- has ProductPriceHistory
- has InventoryItem
- appears in OrderItem and SaleItem

Order
- belongs to an optional customer
- has optional creator
- has OrderItems
- may convert to one Sale through `Sale.source_order`
- may have Payment records
- may be referenced by Notifications

Sale
- may belong to a customer
- has cashier
- has SaleItems
- may originate from one Order
- has payment fields
- affects inventory on completion

Payment
- belongs to exactly one of Sale or Order
- may reference customer and cashier
- has payment method/status/reference/metadata
- may have a unique nullable idempotency key for safe creation retries

CreditAccount
- one-to-one with customer
- has CreditTransactions
- transactions may reference Sale/Payment

Expense
- records historical business expenditure and recorder

Delivery
- one-to-one with Order; records destination, zone, fee snapshot, rider, delivery status, and proof-of-delivery metadata
- has timestamped DeliveryStatusHistory events
- has DeliveryAssignment records for each rider assignment attempt; assignment rows protect delivery and rider history from deletion
- RiderProfile is one-to-one with a RIDER user; DeliveryZone holds configurable area and fee data

Request
- belongs to customer
- may reference product and assigned staff

Notification / ActivityLog
- use Django ContentTypes for generic related objects.

## Important Constraints
- OrderItem and SaleItem preserve product name/SKU/price snapshots.
- Payment must belong to exactly one transaction type.
- Non-null Payment idempotency keys are unique.
- Historical completed/refunded payments cannot be casually deleted.
- Historical completed sales/expenses/requests should be preserved according to model rules.
