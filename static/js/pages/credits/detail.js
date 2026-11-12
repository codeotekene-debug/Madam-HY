/**
 * MADAM HY - Credit detail interactions.
 * Production-grade credit details view powered by backend ledger data.
 */

document.addEventListener('DOMContentLoaded', () => {
    let accountData = null;
    let transactionsData = [];

    const accountEl = document.getElementById('creditAccountJson');
    const transactionsEl = document.getElementById('creditTransactionsJson');

    if (accountEl && accountEl.textContent.trim()) {
        try {
            accountData = JSON.parse(accountEl.textContent);
        } catch (e) {
            console.error('Failed to parse credit account JSON:', e);
        }
    }

    if (transactionsEl && transactionsEl.textContent.trim()) {
        try {
            transactionsData = JSON.parse(transactionsEl.textContent);
        } catch (e) {
            console.error('Failed to parse credit transactions JSON:', e);
        }
    }

    // If server rendered already populated HTML, we only update dynamic fields if JSON was present
    if (accountData) {
        const detailCustomerName = document.getElementById('detailCustomerName');
        const detailCustomerPhone = document.getElementById('detailCustomerPhone');
        const detailCreditStatus = document.getElementById('detailCreditStatus');
        const detailCreditLimit = document.getElementById('detailCreditLimit');
        const detailAmountUsed = document.getElementById('detailAmountUsed');
        const detailAvailableCredit = document.getElementById('detailAvailableCredit');
        const detailAccountStatus = document.getElementById('detailAccountStatus');
        const detailOutstanding = document.getElementById('detailOutstanding');
        const detailDueDate = document.getElementById('detailDueDate');

        const custName = accountData.customer?.full_name || accountData.customer?.username || 'Walk-in Customer';
        const custPhone = accountData.customer?.phone_number || accountData.customer?.email || '-';
        const status = accountData.status_display || accountData.status || 'Active';
        const limit = Number(accountData.credit_limit) || 0;
        const outstanding = Number(accountData.outstanding_balance) || 0;
        const available = accountData.available_credit != null ? Number(accountData.available_credit) : Math.max(0, limit - outstanding);

        if (detailCustomerName) detailCustomerName.textContent = custName;
        if (detailCustomerPhone) detailCustomerPhone.textContent = custPhone;
        if (detailCreditStatus) {
            detailCreditStatus.textContent = status;
            detailCreditStatus.className = `status-pill ${status.toLowerCase().replace(/\s+/g, '-')}`;
        }
        if (detailCreditLimit) detailCreditLimit.textContent = `₦ ${formatCurrency(limit)}`;
        if (detailAmountUsed) detailAmountUsed.textContent = `₦ ${formatCurrency(outstanding)}`;
        if (detailAvailableCredit) detailAvailableCredit.textContent = `₦ ${formatCurrency(available)}`;
        if (detailAccountStatus) detailAccountStatus.textContent = status;
        if (detailOutstanding) detailOutstanding.textContent = `₦ ${formatCurrency(outstanding)}`;
        if (detailDueDate && accountData.next_due_date) {
            detailDueDate.textContent = formatDate(accountData.next_due_date);
        }
    }

    if (transactionsData && transactionsData.length > 0) {
        const detailTransactionsBody = document.getElementById('detailTransactionsBody');
        if (detailTransactionsBody) {
            detailTransactionsBody.innerHTML = transactionsData.map(txn => {
                const isDebit = txn.transaction_type === 'CREDIT_PURCHASE';
                const sign = isDebit ? '+' : '-';
                const amtColor = isDebit ? 'color: #be123c;' : 'color: #057a44;';
                return `
                    <tr>
                        <td>${formatDate(txn.created_at)}</td>
                        <td><span class="status-pill status-pill-sm">${escapeHtml(txn.transaction_type_display || txn.transaction_type)}</span></td>
                        <td class="num" style="${amtColor}">${sign}₦ ${formatCurrency(Math.abs(Number(txn.amount)))}</td>
                        <td class="num">₦ ${formatCurrency(Number(txn.new_balance))}</td>
                    </tr>
                `;
            }).join('');
        }
    }
});

function formatDate(value) {
    if (!value) return '-';
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    const num = Number(value) || 0;
    return num.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
