/**
 * MADAM HY - Payment detail interactions.
 * Frontend-only demo data for payment details view.
 */

const paymentDetailData = {
    reference: 'PAY-MH-2601',
    date: '2026-08-14',
    orderNumber: 'MH-ORD-10501',
    customer: 'Aisha Bello',
    customerPhone: '0803 555 0102',
    paymentMethod: 'Cash',
    amountPaid: 40000,
    status: 'Successful',
    cashier: 'Amina Yusuf',
    orderTotal: 42500,
    orderDate: '2026-08-14'
};

document.addEventListener('DOMContentLoaded', () => {
    const detailPaymentRef = document.getElementById('detailPaymentRef');
    const detailPaymentDate = document.getElementById('detailPaymentDate');
    const detailPaymentStatus = document.getElementById('detailPaymentStatus');
    const detailOrderRef = document.getElementById('detailOrderRef');
    const detailCustomer = document.getElementById('detailCustomer');
    const detailCustomerPhone = document.getElementById('detailCustomerPhone');
    const detailPaymentDateField = document.getElementById('detailPaymentDateField');
    const detailPaymentMethod = document.getElementById('detailPaymentMethod');
    const detailAmountPaid = document.getElementById('detailAmountPaid');
    const detailStatusField = document.getElementById('detailStatusField');
    const detailCashier = document.getElementById('detailCashier');
    const detailOrderNumber = document.getElementById('detailOrderNumber');
    const detailOrderDate = document.getElementById('detailOrderDate');
    const detailOrderTotal = document.getElementById('detailOrderTotal');
    const timelineEvent = document.getElementById('timelineEvent');
    const timelineTime = document.getElementById('timelineTime');

    if (detailPaymentRef) detailPaymentRef.textContent = `Payment ${paymentDetailData.reference}`;
    if (detailPaymentDate) detailPaymentDate.textContent = formatDate(paymentDetailData.date);
    if (detailPaymentStatus) {
        detailPaymentStatus.textContent = paymentDetailData.status;
        detailPaymentStatus.className = `status-pill ${paymentDetailData.status.toLowerCase()}`;
    }
    if (detailOrderRef) detailOrderRef.textContent = paymentDetailData.orderNumber;
    if (detailCustomer) detailCustomer.textContent = paymentDetailData.customer;
    if (detailCustomerPhone) detailCustomerPhone.textContent = paymentDetailData.customerPhone;
    if (detailPaymentDateField) detailPaymentDateField.textContent = formatDate(paymentDetailData.date);
    if (detailPaymentMethod) detailPaymentMethod.textContent = paymentDetailData.paymentMethod;
    if (detailAmountPaid) detailAmountPaid.textContent = `₦ ${formatCurrency(paymentDetailData.amountPaid)}`;
    if (detailStatusField) detailStatusField.textContent = paymentDetailData.status;
    if (detailCashier) detailCashier.textContent = paymentDetailData.cashier;
    if (detailOrderNumber) detailOrderNumber.textContent = paymentDetailData.orderNumber;
    if (detailOrderDate) detailOrderDate.textContent = formatDate(paymentDetailData.orderDate);
    if (detailOrderTotal) detailOrderTotal.textContent = `₦ ${formatCurrency(paymentDetailData.orderTotal)}`;

    if (timelineEvent) timelineEvent.textContent = `Payment ${paymentDetailData.status.toLowerCase()}`;
    if (timelineTime) timelineTime.textContent = `${formatDate(paymentDetailData.date)} at ${formatTime(paymentDetailData.date)}`;
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatTime(value) {
    return new Date(value).toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
