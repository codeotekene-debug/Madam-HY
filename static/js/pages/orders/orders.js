/**
 * MADAM HY - Orders list interactions.
 * Frontend-only demo data for order browsing and filtering.
 */

const ordersData = [
    {
        orderNumber: 'MH-ORD-10501',
        customer: 'Aisha Bello',
        date: '2026-08-14',
        items: 3,
        total: 42500,
        status: 'Completed',
        payment: 'Cash',
        cashier: 'Amina Yusuf'
    },
    {
        orderNumber: 'MH-ORD-10502',
        customer: 'Musa Adamu',
        date: '2026-08-14',
        items: 2,
        total: 31800,
        status: 'Processing',
        payment: 'Card',
        cashier: 'David Okafor'
    },
    {
        orderNumber: 'MH-ORD-10503',
        customer: 'Grace Nnaji',
        date: '2026-08-13',
        items: 1,
        total: 28000,
        status: 'Completed',
        payment: 'Transfer',
        cashier: 'Amina Yusuf'
    },
    {
        orderNumber: 'MH-ORD-10504',
        customer: 'Emeka Ibe',
        date: '2026-08-13',
        items: 4,
        total: 52300,
        status: 'Ready',
        payment: 'Cash',
        cashier: 'David Okafor'
    },
    {
        orderNumber: 'MH-ORD-10505',
        customer: 'Zainab Hassan',
        date: '2026-08-12',
        items: 2,
        total: 18900,
        status: 'Pending',
        payment: 'Credit',
        cashier: 'Amina Yusuf'
    },
    {
        orderNumber: 'MH-ORD-10506',
        customer: 'James Obi',
        date: '2026-08-12',
        items: 5,
        total: 67500,
        status: 'Confirmed',
        payment: 'Transfer',
        cashier: 'David Okafor'
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderOrdersSummary();
    renderOrdersTable();
    bindOrdersFilters();
});

function bindOrdersFilters() {
    const searchInput = document.getElementById('ordersSearch');
    const statusFilter = document.getElementById('ordersStatusFilter');
    const paymentFilter = document.getElementById('ordersPaymentFilter');

    const update = () => renderOrdersTable();

    searchInput?.addEventListener('input', update);
    statusFilter?.addEventListener('change', update);
    paymentFilter?.addEventListener('change', update);
}

function renderOrdersSummary() {
    const totalCount = document.getElementById('totalOrdersCount');
    const pendingCount = document.getElementById('pendingOrdersCount');
    const completedCount = document.getElementById('completedOrdersCount');
    const totalValue = document.getElementById('totalOrderValue');

    if (totalCount) totalCount.textContent = String(ordersData.length);
    if (pendingCount) pendingCount.textContent = String(ordersData.filter(o => o.status === 'Pending').length);
    if (completedCount) completedCount.textContent = String(ordersData.filter(o => o.status === 'Completed').length);
    if (totalValue) totalValue.textContent = `₦ ${formatCurrency(ordersData.reduce((sum, o) => sum + o.total, 0))}`;
}

function renderOrdersTable() {
    const tableBody = document.getElementById('ordersTableBody');
    const emptyState = document.getElementById('ordersEmptyState');
    const searchInput = document.getElementById('ordersSearch');
    const statusFilter = document.getElementById('ordersStatusFilter');
    const paymentFilter = document.getElementById('ordersPaymentFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const statusValue = statusFilter?.value || 'all';
    const paymentValue = paymentFilter?.value || 'all';

    let filtered = ordersData.filter(order => {
        const matchesQuery = !query || [order.orderNumber, order.customer, order.cashier].some(value => value.toLowerCase().includes(query));
        const matchesStatus = statusValue === 'all' || order.status === statusValue;
        const matchesPayment = paymentValue === 'all' || order.payment === paymentValue;
        return matchesQuery && matchesStatus && matchesPayment;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(order => `
        <tr>
            <td data-label="Order #">${order.orderNumber}</td>
            <td data-label="Customer">${order.customer}</td>
            <td data-label="Date">${formatDate(order.date)}</td>
            <td data-label="Items">${order.items}</td>
            <td data-label="Total">₦ ${formatCurrency(order.total)}</td>
            <td data-label="Order status"><span class="status-pill ${order.status.toLowerCase()}">${order.status}</span></td>
            <td data-label="Payment"><span class="payment-badge">${order.payment}</span></td>
            <td data-label="Action"><a href="#" class="action-link\">View</a></td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
