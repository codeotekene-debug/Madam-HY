/**
 * MADAM HY - Payment success interactions.
 * Frontend-only demo data for successful payment confirmation.
 */

const paymentSuccessData = {
    reference: 'PAY-MH-2601',
    orderNumber: 'MH-ORD-10501',
    amount: 40000,
    paymentMethod: 'Cash',
    date: '2026-08-14',
    time: '14:32'
};

document.addEventListener('DOMContentLoaded', () => {
    const successPaymentRef = document.getElementById('successPaymentRef');
    const successAmount = document.getElementById('successAmount');
    const successOrderNumber = document.getElementById('successOrderNumber');
    const successDateTime = document.getElementById('successDateTime');
    const successPaymentMethod = document.getElementById('successPaymentMethod');

    if (successPaymentRef) successPaymentRef.textContent = paymentSuccessData.reference;
    if (successAmount) successAmount.textContent = `₦ ${formatCurrency(paymentSuccessData.amount)}`;
    if (successOrderNumber) successOrderNumber.textContent = paymentSuccessData.orderNumber;
    if (successDateTime) successDateTime.textContent = `${formatDate(paymentSuccessData.date)} at ${paymentSuccessData.time}`;
    if (successPaymentMethod) successPaymentMethod.textContent = paymentSuccessData.paymentMethod;
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
