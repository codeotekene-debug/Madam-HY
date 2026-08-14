const salesHistoryData = [
    {
        saleNumber: 'MH-10241',
        customer: 'Aisha Bello',
        cashier: 'Amina Yusuf',
        date: '2026-08-14',
        payment: 'Cash',
        status: 'Completed',
        total: 42500,
        items: [
            { name: 'Radiant Glow Serum', qty: 2, price: 9500 },
            { name: 'Green Ankara Fabric Premium', qty: 1, price: 12500 },
            { name: 'Leather Office Tote', qty: 1, price: 18500 }
        ]
    },
    {
        saleNumber: 'MH-10242',
        customer: 'Musa Adamu',
        cashier: 'Amina Yusuf',
        date: '2026-08-14',
        payment: 'Card',
        status: 'Pending',
        total: 31800,
        items: [
            { name: 'Wireless Speaker Mini', qty: 1, price: 22000 },
            { name: 'Kitchen Storage Basket', qty: 1, price: 6200 },
            { name: 'Leather Office Tote', qty: 1, price: 18500 }
        ]
    },
    {
        saleNumber: 'MH-10243',
        customer: 'Grace Nnaji',
        cashier: 'David Okafor',
        date: '2026-08-13',
        payment: 'Transfer',
        status: 'Completed',
        total: 28000,
        items: [
            { name: 'Velvet Evening Gown', qty: 1, price: 28000 }
        ]
    },
    {
        saleNumber: 'MH-10244',
        customer: 'Emeka Ibe',
        cashier: 'Amina Yusuf',
        date: '2026-08-13',
        payment: 'Cash',
        status: 'Refunded',
        total: 19000,
        items: [
            { name: 'Kitchen Storage Basket', qty: 1, price: 6200 },
            { name: 'Radiant Glow Serum', qty: 1, price: 9500 },
            { name: 'Green Ankara Fabric Premium', qty: 1, price: 12500 }
        ]
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderSalesSummary();
    renderSalesTable();
    bindHistoryFilters();
});

function bindHistoryFilters() {
    const searchInput = document.getElementById('historySearch');
    const paymentFilter = document.getElementById('historyPaymentFilter');
    const statusFilter = document.getElementById('historyStatusFilter');

    searchInput?.addEventListener('input', renderSalesTable);
    paymentFilter?.addEventListener('change', renderSalesTable);
    statusFilter?.addEventListener('change', renderSalesTable);
}

function renderSalesSummary() {
    const totalSalesCount = document.getElementById('totalSalesCount');
    const cashSalesCount = document.getElementById('cashSalesCount');
    const cardSalesCount = document.getElementById('cardSalesCount');
    const revenueTotal = document.getElementById('revenueTotal');

    if (totalSalesCount) totalSalesCount.textContent = String(salesHistoryData.length);
    if (cashSalesCount) cashSalesCount.textContent = String(salesHistoryData.filter(item => item.payment === 'Cash').length);
    if (cardSalesCount) cardSalesCount.textContent = String(salesHistoryData.filter(item => item.payment === 'Card').length);
    if (revenueTotal) revenueTotal.textContent = `₦ ${formatCurrency(salesHistoryData.reduce((sum, item) => sum + item.total, 0))}`;
}

function renderSalesTable() {
    const tableBody = document.getElementById('historyTableBody');
    const emptyState = document.getElementById('historyEmptyState');
    const searchInput = document.getElementById('historySearch');
    const paymentFilter = document.getElementById('historyPaymentFilter');
    const statusFilter = document.getElementById('historyStatusFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const paymentValue = paymentFilter?.value || 'all';
    const statusValue = statusFilter?.value || 'all';

    const filtered = salesHistoryData.filter(item => {
        const matchesPayment = paymentValue === 'all' || item.payment === paymentValue;
        const matchesStatus = statusValue === 'all' || item.status === statusValue;
        const matchQuery = !query || [item.saleNumber, item.customer, item.cashier].some(value => value.toLowerCase().includes(query));
        return matchesPayment && matchesStatus && matchQuery;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(item => `
        <tr>
            <td>${item.saleNumber}</td>
            <td>${item.customer}</td>
            <td>${item.cashier}</td>
            <td>${formatDate(item.date)}</td>
            <td>${item.payment}</td>
            <td><span class="status-pill ${item.status.toLowerCase()}">${item.status}</span></td>
            <td>₦ ${formatCurrency(item.total)}</td>
            <td><a href="#" class="action-link">View</a></td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
