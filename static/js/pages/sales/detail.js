const salesDetailData = {
    saleNumber: 'MH-10241',
    date: '2026-08-14',
    cashiers: 'Amina Yusuf',
    customer: 'Aisha Bello',
    payment: 'Cash',
    status: 'Completed',
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
    const detailSaleNumber = document.getElementById('detailSaleNumber');
    const detailDate = document.getElementById('detailDate');
    const detailStatus = document.getElementById('detailStatus');
    const detailCustomer = document.getElementById('detailCustomer');
    const detailCashier = document.getElementById('detailCashier');
    const detailPayment = document.getElementById('detailPayment');
    const detailSubtotal = document.getElementById('detailSubtotal');
    const detailDiscount = document.getElementById('detailDiscount');
    const detailTotal = document.getElementById('detailTotal');
    const detailItemsBody = document.getElementById('detailItemsBody');

    if (detailSaleNumber) detailSaleNumber.textContent = `Sale #${salesDetailData.saleNumber}`;
    if (detailDate) detailDate.textContent = formatDate(salesDetailData.date);
    if (detailStatus) {
        detailStatus.textContent = salesDetailData.status;
        detailStatus.className = `status-pill ${salesDetailData.status.toLowerCase()}`;
    }
    if (detailCustomer) detailCustomer.textContent = salesDetailData.customer;
    if (detailCashier) detailCashier.textContent = salesDetailData.cashiers;
    if (detailPayment) detailPayment.textContent = salesDetailData.payment;
    if (detailSubtotal) detailSubtotal.textContent = `₦ ${formatCurrency(salesDetailData.subtotal)}`;
    if (detailDiscount) detailDiscount.textContent = `₦ ${formatCurrency(salesDetailData.discount)}`;
    if (detailTotal) detailTotal.textContent = `₦ ${formatCurrency(salesDetailData.total)}`;

    if (detailItemsBody) {
        detailItemsBody.innerHTML = salesDetailData.items.map(item => `
            <tr>
                <td>${item.name}</td>
                <td>${item.qty}</td>
                <td>₦ ${formatCurrency(item.price)}</td>
                <td>₦ ${formatCurrency(item.qty * item.price)}</td>
            </tr>
        `).join('');
    }
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
