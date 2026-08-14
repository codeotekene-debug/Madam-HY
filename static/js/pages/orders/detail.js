/**
 * MADAM HY - Order detail interactions.
 * Frontend-only demo data for order details view.
 */

const orderDetailData = {
    orderNumber: 'MH-ORD-10501',
    date: '2026-08-14',
    customer: 'Aisha Bello',
    phone: '0803 555 0102',
    address: '15 Lekki Phase 1, Lagos',
    paymentMethod: 'Cash',
    paymentStatus: 'Paid',
    status: 'Completed',
    assignedStaff: 'Amina Yusuf',
    subtotal: 42500,
    discount: 2500,
    total: 40000,
    items: [
        { name: 'Radiant Glow Serum', qty: 2, price: 9500 },
        { name: 'Green Ankara Fabric Premium', qty: 1, price: 12500 },
        { name: 'Leather Office Tote', qty: 1, price: 18500 }
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    const detailOrderNumber = document.getElementById('detailOrderNumber');
    const detailOrderDate = document.getElementById('detailOrderDate');
    const detailOrderStatus = document.getElementById('detailOrderStatus');
    const detailCustomer = document.getElementById('detailCustomer');
    const detailPhone = document.getElementById('detailPhone');
    const detailDateField = document.getElementById('detailDateField');
    const detailAddress = document.getElementById('detailAddress');
    const detailPaymentMethod = document.getElementById('detailPaymentMethod');
    const detailPaymentStatus = document.getElementById('detailPaymentStatus');
    const detailStatusField = document.getElementById('detailStatusField');
    const detailAssignedStaff = document.getElementById('detailAssignedStaff');
    const detailItemsBody = document.getElementById('detailItemsBody');
    const detailSubtotal = document.getElementById('detailSubtotal');
    const detailDiscount = document.getElementById('detailDiscount');
    const detailTotal = document.getElementById('detailTotal');

    if (detailOrderNumber) detailOrderNumber.textContent = `Order #${orderDetailData.orderNumber}`;
    if (detailOrderDate) detailOrderDate.textContent = formatDate(orderDetailData.date);
    if (detailOrderStatus) {
        detailOrderStatus.textContent = orderDetailData.status;
        detailOrderStatus.className = `status-pill ${orderDetailData.status.toLowerCase()}`;
    }
    if (detailCustomer) detailCustomer.textContent = orderDetailData.customer;
    if (detailPhone) detailPhone.textContent = orderDetailData.phone;
    if (detailDateField) detailDateField.textContent = formatDate(orderDetailData.date);
    if (detailAddress) detailAddress.textContent = orderDetailData.address;
    if (detailPaymentMethod) detailPaymentMethod.textContent = orderDetailData.paymentMethod;
    if (detailPaymentStatus) detailPaymentStatus.textContent = orderDetailData.paymentStatus;
    if (detailStatusField) detailStatusField.textContent = orderDetailData.status;
    if (detailAssignedStaff) detailAssignedStaff.textContent = orderDetailData.assignedStaff;

    if (detailItemsBody) {
        detailItemsBody.innerHTML = orderDetailData.items.map(item => `
            <tr>
                <td>${item.name}</td>
                <td>${item.qty}</td>
                <td>₦ ${formatCurrency(item.price)}</td>
                <td>₦ ${formatCurrency(item.qty * item.price)}</td>
            </tr>
        `).join('');
    }

    if (detailSubtotal) detailSubtotal.textContent = `₦ ${formatCurrency(orderDetailData.subtotal)}`;
    if (detailDiscount) detailDiscount.textContent = `₦ ${formatCurrency(orderDetailData.discount)}`;
    if (detailTotal) detailTotal.textContent = `₦ ${formatCurrency(orderDetailData.total)}`;
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
