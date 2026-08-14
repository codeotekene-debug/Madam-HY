/**
 * MADAM HY - Payment failed interactions.
 * Frontend-only demo data for failed payment confirmation.
 */

const paymentFailedData = {
    reference: 'PAY-MH-2607',
    orderNumber: 'MH-ORD-10507',
    amount: 25500,
    date: '2026-08-14',
    time: '15:45',
    reason: 'Insufficient funds on payment method'
};

document.addEventListener('DOMContentLoaded', () => {
    const failedPaymentRef = document.getElementById('failedPaymentRef');
    const failedOrderNumber = document.getElementById('failedOrderNumber');
    const failedAmount = document.getElementById('failedAmount');
    const failedDateTime = document.getElementById('failedDateTime');
    const failedReason = document.getElementById('failedReason');

    if (failedPaymentRef) failedPaymentRef.textContent = paymentFailedData.reference;
    if (failedOrderNumber) failedOrderNumber.textContent = paymentFailedData.orderNumber;
    if (failedAmount) failedAmount.textContent = `₦ ${formatCurrency(paymentFailedData.amount)}`;
    if (failedDateTime) failedDateTime.textContent = `${formatDate(paymentFailedData.date)} at ${paymentFailedData.time}`;
    if (failedReason) failedReason.textContent = paymentFailedData.reason;
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
