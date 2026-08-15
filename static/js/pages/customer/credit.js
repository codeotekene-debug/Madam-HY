/**
 * MADAM HY - Customer Credit
 * Frontend-only customer credit information
 */

const creditData = {
    creditLimit: 100000,
    usedCredit: 15000,
    availableCredit: 85000,
    outstandingBalance: 15000,
    status: 'Active',
    lastPaymentDate: '2026-08-10',
    nextPaymentDue: '2026-09-10'
};

const paymentHistory = [
    { date: '2026-08-10', description: 'Credit payment', amount: 5000, status: 'Completed' },
    { date: '2026-07-28', description: 'Credit purchase', amount: -12500, status: 'Completed' },
    { date: '2026-07-10', description: 'Credit payment', amount: 8000, status: 'Completed' },
    { date: '2026-06-25', description: 'Credit purchase', amount: -20000, status: 'Completed' }
];

document.addEventListener('DOMContentLoaded', () => {
    renderCredit();
});

function renderCredit() {
    // Summary
    document.getElementById('creditLimit')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(creditData.creditLimit)}`));
    document.getElementById('usedCredit')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(creditData.usedCredit)}`));
    document.getElementById('availableCreditAmount')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(creditData.availableCredit)}`));
    document.getElementById('outstandingBalance')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(creditData.outstandingBalance)}`));

    // Details
    document.getElementById('creditStatus')?.replaceChildren(document.createTextNode(creditData.status));
    document.getElementById('lastPaymentDate')?.replaceChildren(document.createTextNode(formatDate(creditData.lastPaymentDate)));
    document.getElementById('nextPaymentDue')?.replaceChildren(document.createTextNode(formatDate(creditData.nextPaymentDue)));

    // History
    const historyBody = document.getElementById('creditHistoryBody');
    const historyEmpty = document.getElementById('creditHistoryEmpty');

    if (historyBody && paymentHistory.length > 0) {
        historyBody.innerHTML = paymentHistory.map(item => `
            <tr>
                <td>${formatDate(item.date)}</td>
                <td>${item.description}</td>
                <td>${item.amount > 0 ? '+' : ''}₦${formatCurrency(Math.abs(item.amount))}</td>
                <td><span class="badge badge-primary">${item.status}</span></td>
            </tr>
        `).join('');
        historyEmpty?.classList.add('empty-state-hidden');
    }
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
