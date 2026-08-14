/**
 * MADAM HY - Credit detail interactions.
 * Frontend-only demo data for credit details view.
 */

const creditDetailData = {
    id: 'CRD-001',
    customer: 'Aisha Bello',
    phone: '0803 555 0102',
    creditLimit: 150000,
    amountUsed: 85000,
    availableCredit: 65000,
    totalIssued: 85000,
    totalPaid: 35000,
    outstandingBalance: 50000,
    dueDate: '2026-09-14',
    status: 'Active',
    isOverdue: false,
    overdueAmount: 0,
    daysOverdue: 0,
    transactions: [
        { date: '2026-08-14', type: 'Payment', amount: -10000, balance: 40000 },
        { date: '2026-08-10', type: 'Credit', amount: 15000, balance: 50000 },
        { date: '2026-08-05', type: 'Payment', amount: -25000, balance: 35000 },
        { date: '2026-07-28', type: 'Credit', amount: 35000, balance: 60000 },
        { date: '2026-07-20', type: 'Payment', amount: -10000, balance: 25000 },
        { date: '2026-07-15', type: 'Credit', amount: 50000, balance: 35000 }
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    const detailCustomerName = document.getElementById('detailCustomerName');
    const detailCustomerPhone = document.getElementById('detailCustomerPhone');
    const detailCreditStatus = document.getElementById('detailCreditStatus');
    const detailCreditLimit = document.getElementById('detailCreditLimit');
    const detailAmountUsed = document.getElementById('detailAmountUsed');
    const detailAvailableCredit = document.getElementById('detailAvailableCredit');
    const detailAccountStatus = document.getElementById('detailAccountStatus');
    const detailTotalIssued = document.getElementById('detailTotalIssued');
    const detailTotalPaid = document.getElementById('detailTotalPaid');
    const detailOutstanding = document.getElementById('detailOutstanding');
    const detailDueDate = document.getElementById('detailDueDate');
    const detailOverdueAmount = document.getElementById('detailOverdueAmount');
    const detailDaysOverdue = document.getElementById('detailDaysOverdue');
    const detailTransactionsBody = document.getElementById('detailTransactionsBody');

    if (detailCustomerName) detailCustomerName.textContent = creditDetailData.customer;
    if (detailCustomerPhone) detailCustomerPhone.textContent = creditDetailData.phone;
    if (detailCreditStatus) {
        detailCreditStatus.textContent = creditDetailData.status;
        detailCreditStatus.className = `status-pill ${creditDetailData.status.toLowerCase().replace(' ', '-')}`;
    }
    if (detailCreditLimit) detailCreditLimit.textContent = `₦ ${formatCurrency(creditDetailData.creditLimit)}`;
    if (detailAmountUsed) detailAmountUsed.textContent = `₦ ${formatCurrency(creditDetailData.amountUsed)}`;
    if (detailAvailableCredit) detailAvailableCredit.textContent = `₦ ${formatCurrency(creditDetailData.availableCredit)}`;
    if (detailAccountStatus) detailAccountStatus.textContent = creditDetailData.status;
    if (detailTotalIssued) detailTotalIssued.textContent = `₦ ${formatCurrency(creditDetailData.totalIssued)}`;
    if (detailTotalPaid) detailTotalPaid.textContent = `₦ ${formatCurrency(creditDetailData.totalPaid)}`;
    if (detailOutstanding) detailOutstanding.textContent = `₦ ${formatCurrency(creditDetailData.outstandingBalance)}`;
    if (detailDueDate) detailDueDate.textContent = formatDate(creditDetailData.dueDate);
    if (detailOverdueAmount) detailOverdueAmount.textContent = `₦ ${formatCurrency(creditDetailData.overdueAmount)}`;
    if (detailDaysOverdue) detailDaysOverdue.textContent = `${creditDetailData.daysOverdue} days`;

    if (detailTransactionsBody) {
        detailTransactionsBody.innerHTML = creditDetailData.transactions.map(txn => `
            <tr>
                <td>${formatDate(txn.date)}</td>
                <td>${txn.type}</td>
                <td>${txn.type === 'Credit' ? '+' : '-'}₦ ${formatCurrency(Math.abs(txn.amount))}</td>
                <td>₦ ${formatCurrency(txn.balance)}</td>
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
