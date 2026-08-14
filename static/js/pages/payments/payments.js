/**
 * MADAM HY - Payments list interactions.
 * Frontend-only demo data for payment browsing and filtering.
 */

const paymentsData = [
    {
        reference: 'PAY-MH-2601',
        orderNumber: 'MH-ORD-10501',
        customer: 'Aisha Bello',
        date: '2026-08-14',
        amount: 40000,
        method: 'Cash',
        status: 'Successful',
        cashier: 'Amina Yusuf'
    },
    {
        reference: 'PAY-MH-2602',
        orderNumber: 'MH-ORD-10502',
        customer: 'Musa Adamu',
        date: '2026-08-14',
        amount: 31800,
        method: 'Card',
        status: 'Processing',
        cashier: 'David Okafor'
    },
    {
        reference: 'PAY-MH-2603',
        orderNumber: 'MH-ORD-10503',
        customer: 'Grace Nnaji',
        date: '2026-08-13',
        amount: 28000,
        method: 'Transfer',
        status: 'Successful',
        cashier: 'Amina Yusuf'
    },
    {
        reference: 'PAY-MH-2604',
        orderNumber: 'MH-ORD-10504',
        customer: 'Emeka Ibe',
        date: '2026-08-13',
        amount: 52300,
        method: 'Cash',
        status: 'Successful',
        cashier: 'David Okafor'
    },
    {
        reference: 'PAY-MH-2605',
        orderNumber: 'MH-ORD-10505',
        customer: 'Zainab Hassan',
        date: '2026-08-12',
        amount: 18900,
        method: 'Credit',
        status: 'Pending',
        cashier: 'Amina Yusuf'
    },
    {
        reference: 'PAY-MH-2606',
        orderNumber: 'MH-ORD-10506',
        customer: 'James Obi',
        date: '2026-08-12',
        amount: 67500,
        method: 'Transfer',
        status: 'Successful',
        cashier: 'David Okafor'
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderPaymentsSummary();
    renderPaymentsTable();
    bindPaymentsFilters();
});

function bindPaymentsFilters() {
    const searchInput = document.getElementById('paymentsSearch');
    const statusFilter = document.getElementById('paymentsStatusFilter');
    const methodFilter = document.getElementById('paymentsMethodFilter');

    const update = () => renderPaymentsTable();

    searchInput?.addEventListener('input', update);
    statusFilter?.addEventListener('change', update);
    methodFilter?.addEventListener('change', update);
}

function renderPaymentsSummary() {
    const totalCount = document.getElementById('totalPaymentsCount');
    const successfulCount = document.getElementById('successfulPaymentsCount');
    const pendingCount = document.getElementById('pendingPaymentsCount');
    const totalAmount = document.getElementById('totalPaymentAmount');

    if (totalCount) totalCount.textContent = String(paymentsData.length);
    if (successfulCount) successfulCount.textContent = String(paymentsData.filter(p => p.status === 'Successful').length);
    if (pendingCount) pendingCount.textContent = String(paymentsData.filter(p => p.status === 'Pending').length);
    if (totalAmount) totalAmount.textContent = `₦ ${formatCurrency(paymentsData.reduce((sum, p) => sum + p.amount, 0))}`;
}

function renderPaymentsTable() {
    const tableBody = document.getElementById('paymentsTableBody');
    const emptyState = document.getElementById('paymentsEmptyState');
    const searchInput = document.getElementById('paymentsSearch');
    const statusFilter = document.getElementById('paymentsStatusFilter');
    const methodFilter = document.getElementById('paymentsMethodFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const statusValue = statusFilter?.value || 'all';
    const methodValue = methodFilter?.value || 'all';

    let filtered = paymentsData.filter(payment => {
        const matchesQuery = !query || [payment.reference, payment.orderNumber, payment.customer].some(value => value.toLowerCase().includes(query));
        const matchesStatus = statusValue === 'all' || payment.status === statusValue;
        const matchesMethod = methodValue === 'all' || payment.method === methodValue;
        return matchesQuery && matchesStatus && matchesMethod;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(payment => `
        <tr>
            <td data-label="Reference">${payment.reference}</td>
            <td data-label="Order #">${payment.orderNumber}</td>
            <td data-label="Customer">${payment.customer}</td>
            <td data-label="Date">${formatDate(payment.date)}</td>
            <td data-label="Amount">₦ ${formatCurrency(payment.amount)}</td>
            <td data-label="Method"><span class="method-badge">${payment.method}</span></td>
            <td data-label="Status"><span class="status-pill ${payment.status.toLowerCase()}">${payment.status}</span></td>
            <td data-label="Action"><a href="#" class="action-link">View</a></td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
