from enum import Enum

from django.core.exceptions import ValidationError
from django.db.models import Count

from apps.orders.models import Order
from apps.sales.models import Sale

from .models import Payment
from .services import PaymentService


class ReconciliationClassification(str, Enum):
    UNPAID = 'UNPAID'
    PARTIALLY_PAID = 'PARTIALLY_PAID'
    FULLY_PAID = 'FULLY_PAID'
    OVERPAID = 'OVERPAID'


class ReconciliationService:
    """Read-only internal financial evaluation for an existing Order or Sale."""

    @classmethod
    def _validate_transaction(cls, transaction):
        if not isinstance(transaction, (Order, Sale)) or transaction.pk is None:
            raise ValidationError({'transaction': 'An existing order or sale is required.'})
        return transaction

    @classmethod
    def _transaction_data(cls, transaction):
        if isinstance(transaction, Order):
            return 'ORDER', transaction.order_number, transaction.payment_status, transaction.status
        return 'SALE', transaction.sale_number, transaction.payment_status, transaction.status

    @classmethod
    def _classification(cls, completed_amount, transaction_total):
        if completed_amount == 0:
            return ReconciliationClassification.UNPAID.value
        if completed_amount > transaction_total:
            return ReconciliationClassification.OVERPAID.value
        if completed_amount == transaction_total:
            return ReconciliationClassification.FULLY_PAID.value
        return ReconciliationClassification.PARTIALLY_PAID.value

    @classmethod
    def _findings(cls, transaction, balance):
        payments = Payment.objects.filter(
            order_id=transaction.pk if isinstance(transaction, Order) else None,
            sale_id=transaction.pk if isinstance(transaction, Sale) else None,
        )
        findings = []

        if balance['overpaid_amount'] > 0:
            findings.append('COMPLETED_PAYMENT_EXCEEDS_TRANSACTION_TOTAL')

        if transaction.customer_id:
            if payments.filter(customer_id__isnull=False).exclude(customer_id=transaction.customer_id).exists():
                findings.append('PAYMENT_CUSTOMER_MISMATCH')

        duplicate_references = payments.exclude(transaction_reference='').values(
            'transaction_reference'
        ).annotate(reference_count=Count('id')).filter(reference_count__gt=1)
        if duplicate_references.exists():
            findings.append('DUPLICATE_TRANSACTION_REFERENCE')

        expected_method = transaction.payment_method
        if expected_method == 'TRANSFER':
            expected_method = Payment.PaymentMethod.BANK_TRANSFER
        if payments.exclude(payment_method=expected_method).exists():
            findings.append('PAYMENT_METHOD_MISMATCH')

        if transaction.status == (Order.OrderStatus.CANCELLED if isinstance(transaction, Order) else Sale.SaleStatus.CANCELLED):
            if payments.filter(payment_status=Payment.PaymentStatus.COMPLETED).exists():
                findings.append('COMPLETED_PAYMENT_ON_CANCELLED_TRANSACTION')

        classification = cls._classification(
            balance['completed_amount'], balance['transaction_total']
        )
        if isinstance(transaction, Order):
            if transaction.payment_status == Order.PaymentStatus.PENDING and classification != ReconciliationClassification.UNPAID.value:
                findings.append('ORDER_PAYMENT_STATUS_MISMATCH')
            if transaction.payment_status == Order.PaymentStatus.CONFIRMED and classification == ReconciliationClassification.UNPAID.value:
                findings.append('ORDER_PAYMENT_STATUS_MISMATCH')
        elif transaction.payment_status == Sale.PaymentStatus.PENDING and classification != ReconciliationClassification.UNPAID.value:
            findings.append('SALE_PAYMENT_STATUS_MISMATCH')
        elif transaction.payment_status == Sale.PaymentStatus.COMPLETED and classification != ReconciliationClassification.FULLY_PAID.value:
            findings.append('SALE_PAYMENT_STATUS_MISMATCH')

        return findings

    @classmethod
    def reconcile(cls, transaction):
        transaction = cls._validate_transaction(transaction)
        balance = PaymentService.get_transaction_balance(transaction)
        transaction_type, identifier, _, _ = cls._transaction_data(transaction)
        payment_filter = {
            'order_id' if isinstance(transaction, Order) else 'sale_id': transaction.pk,
        }
        payments = Payment.objects.filter(**payment_filter)
        counts = payments.values('payment_status').annotate(count=Count('id'))
        count_by_status = {item['payment_status']: item['count'] for item in counts}
        classification = cls._classification(
            balance['completed_amount'], balance['transaction_total']
        )
        return {
            'transaction_type': transaction_type,
            'transaction_id': transaction.pk,
            'transaction_identifier': identifier,
            'transaction_total': balance['transaction_total'],
            'payment_count': payments.count(),
            'completed_payment_count': count_by_status.get(Payment.PaymentStatus.COMPLETED, 0),
            'pending_payment_count': count_by_status.get(Payment.PaymentStatus.PENDING, 0),
            'failed_payment_count': count_by_status.get(Payment.PaymentStatus.FAILED, 0),
            'refunded_payment_count': count_by_status.get(Payment.PaymentStatus.REFUNDED, 0),
            'completed_amount': balance['completed_amount'],
            'pending_amount': balance['pending_amount'],
            'failed_amount': balance['failed_amount'],
            'refunded_amount': balance['refunded_amount'],
            'outstanding_amount': balance['outstanding_amount'],
            'overpaid_amount': balance['overpaid_amount'],
            'classification': classification,
            'inconsistency_findings': cls._findings(transaction, balance),
        }

    @classmethod
    def reconcile_transaction(cls, transaction):
        return cls.reconcile(transaction)
