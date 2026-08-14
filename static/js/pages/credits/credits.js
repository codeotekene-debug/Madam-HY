/**
 * MADAM HY - Credits list interactions.
 * Frontend-only demo data for credit account browsing and filtering.
 */

const creditsData = [
    {
        id: 'CRD-001',
        customer: 'Aisha Bello',
        phone: '0803 555 0102',
        creditLimit: 150000,
        amountUsed: 85000,
        amountPaid: 35000,
        outstandingBalance: 50000,
        dueDate: '2026-09-14',
        status: 'Active',
        isOverdue: false,
        overdueAmount: 0
    },
    {
        id: 'CRD-002',
        customer: 'Musa Adamu',
        phone: '0704 333 2819',
        creditLimit: 200000,
        amountUsed: 120000,
        amountPaid: 120000,
        outstandingBalance: 0,
        dueDate: '2026-08-28',
        status: 'Paid',
        isOverdue: false,
        overdueAmount: 0
    },
    {
        id: 'CRD-003',
        customer: 'Grace Nnaji',
        phone: '0809 876 5432',
        creditLimit: 100000,
        amountUsed: 72500,
        amountPaid: 25000,
        outstandingBalance: 47500,
        dueDate: '2026-09-05',
        status: 'Partially Paid',
        isOverdue: false,
        overdueAmount: 0
    },
    {
        id: 'CRD-004',
        customer: 'Emeka Ibe',
        phone: '0701 234 5678',
        creditLimit: 180000,
        amountUsed: 140000,
        amountPaid: 90000,
        outstandingBalance: 50000,
        dueDate: '2026-08-20',
        status: 'Overdue',
        isOverdue: true,
        overdueAmount: 20000
    },
    {
        id: 'CRD-005',
        customer: 'Zainab Hassan',
        phone: '0815 923 4561',
        creditLimit: 120000,
        amountUsed: 95000,
        amountPaid: 45000,
        outstandingBalance: 50000,
        dueDate: '2026-09-10',
        status: 'Active',
        isOverdue: false,
        overdueAmount: 0
    },
    {
        id: 'CRD-006',
        customer: 'James Obi',
        phone: '0702 555 8899',
        creditLimit: 250000,
        amountUsed: 180000,
        amountPaid: 180000,
        outstandingBalance: 0,
        dueDate: '2026-08-15',
        status: 'Paid',
        isOverdue: false,
        overdueAmount: 0
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderCreditsSummary();
    renderCreditsTable();
    bindCreditsFilters();
});

function bindCreditsFilters() {
    const searchInput = document.getElementById('creditsSearch');
    const statusFilter = document.getElementById('creditsStatusFilter');

    const update = () => renderCreditsTable();

    searchInput?.addEventListener('input', update);
    statusFilter?.addEventListener('change', update);
}

function renderCreditsSummary() {
    const totalIssued = document.getElementById('totalCreditIssued');
    const totalOutstanding = document.getElementById('totalOutstanding');
    const totalOverdue = document.getElementById('totalOverdue');
    const totalAccounts = document.getElementById('totalAccountsCount');

    const issued = creditsData.reduce((sum, c) => sum + c.amountUsed, 0);
    const outstanding = creditsData.reduce((sum, c) => sum + c.outstandingBalance, 0);
    const overdue = creditsData.reduce((sum, c) => sum + c.overdueAmount, 0);

    if (totalIssued) totalIssued.textContent = `₦ ${formatCurrency(issued)}`;
    if (totalOutstanding) totalOutstanding.textContent = `₦ ${formatCurrency(outstanding)}`;
    if (totalOverdue) totalOverdue.textContent = `₦ ${formatCurrency(overdue)}`;
    if (totalAccounts) totalAccounts.textContent = String(creditsData.length);
}

function renderCreditsTable() {
    const tableBody = document.getElementById('creditsTableBody');
    const emptyState = document.getElementById('creditsEmptyState');
    const searchInput = document.getElementById('creditsSearch');
    const statusFilter = document.getElementById('creditsStatusFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const statusValue = statusFilter?.value || 'all';

    let filtered = creditsData.filter(credit => {
        const matchesQuery = !query || [credit.customer, credit.phone].some(value => value.toLowerCase().includes(query));
        const matchesStatus = statusValue === 'all' || credit.status === statusValue;
        return matchesQuery && matchesStatus;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(credit => `
        <tr>
            <td data-label="Customer">${credit.customer}</td>
            <td data-label="Phone">${credit.phone}</td>
            <td data-label="Credit Limit">₦ ${formatCurrency(credit.creditLimit)}</td>
            <td data-label="Used">₦ ${formatCurrency(credit.amountUsed)}</td>
            <td data-label="Available">₦ ${formatCurrency(credit.creditLimit - credit.amountUsed)}</td>
            <td data-label="Outstanding">₦ ${formatCurrency(credit.outstandingBalance)}</td>
            <td data-label="Due Date">${formatDate(credit.dueDate)}</td>
            <td data-label="Status"><span class="status-pill ${credit.status.toLowerCase().replace(' ', '-')}">${credit.status}</span></td>
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
