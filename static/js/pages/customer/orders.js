/**
 * MADAM HY - Customer Orders
 * Frontend-only customer order list
 */

const customerOrdersData = [
    {
        id: 'ORD-2026-0847',
        date: '2026-08-12T10:30:00',
        items: 3,
        total: 28500,
        status: 'Completed',
        payment: 'Card'
    },
    {
        id: 'ORD-2026-0846',
        date: '2026-08-08T14:20:00',
        items: 2,
        total: 12300,
        status: 'Completed',
        payment: 'Transfer'
    },
    {
        id: 'ORD-2026-0845',
        date: '2026-08-05T09:15:00',
        items: 5,
        total: 45200,
        status: 'Processing',
        payment: 'Cash'
    },
    {
        id: 'ORD-2026-0844',
        date: '2026-07-28T11:45:00',
        items: 1,
        total: 18500,
        status: 'Completed',
        payment: 'Card'
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderSummary();
    bindFilters();
    renderTable();
});

function renderSummary() {
    const total = customerOrdersData.length;
    const pending = customerOrdersData.filter(item => item.status === 'Pending' || item.status === 'Processing').length;
    const completed = customerOrdersData.filter(item => item.status === 'Completed').length;
    const totalSpent = customerOrdersData.reduce((sum, item) => sum + item.total, 0);

    document.getElementById('customerTotalOrders')?.replaceChildren(document.createTextNode(String(total)));
    document.getElementById('customerPendingOrders')?.replaceChildren(document.createTextNode(String(pending)));
    document.getElementById('customerCompletedOrders')?.replaceChildren(document.createTextNode(String(completed)));
    document.getElementById('customerTotalSpent')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(totalSpent)}`));
}

function bindFilters() {
    const search = document.getElementById('customerOrdersSearch');
    const status = document.getElementById('customerOrdersStatusFilter');

    const applyFilters = () => renderTable();
    search?.addEventListener('input', applyFilters);
    status?.addEventListener('change', applyFilters);
}

function renderTable() {
    const tableBody = document.getElementById('customerOrdersTableBody');
    const empty = document.getElementById('customerOrdersEmpty');

    if (!tableBody) return;

    const searchValue = document.getElementById('customerOrdersSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('customerOrdersStatusFilter')?.value || 'all';

    let filtered = customerOrdersData.filter(item => {
        const matchesSearch = !searchValue || item.id.toLowerCase().includes(searchValue);
        const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        return;
    }

    empty?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(item => `
        <tr>
            <td><strong>${item.id}</strong></td>
            <td>${formatDate(item.date)}</td>
            <td>${item.items}</td>
            <td>₦${formatCurrency(item.total)}</td>
            <td><span class="order-status ${item.status.toLowerCase().replace(/\s+/g, '-')}">${item.status}</span></td>
            <td><a href="/customer/order/${item.id}/" class="order-action-link">View</a></td>
        </tr>
    `).join('');
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
