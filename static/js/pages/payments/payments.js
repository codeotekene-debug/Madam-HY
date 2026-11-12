/**
 * MADAM HY - Payments list interactions.
 * Production-grade payment browsing, filtering, and live reconciliation tracking.
 */

let paymentsData = [];

document.addEventListener('DOMContentLoaded', () => {
    loadPaymentsData();
    bindPaymentsFilters();
});

async function loadPaymentsData() {
    const paymentsDataEl = document.getElementById('paymentsDataJson');
    if (paymentsDataEl && paymentsDataEl.textContent.trim()) {
        try {
            paymentsData = JSON.parse(paymentsDataEl.textContent);
            renderPaymentsSummary();
            renderPaymentsTable();
            return;
        } catch (e) {
            console.error('Failed to parse payments JSON from DOM:', e);
        }
    }

    // Fallback: fetch from payments API
    try {
        const resp = await fetch('/payments/?format=json');
        if (resp.ok) {
            const json = await resp.json();
            paymentsData = (json.data && json.data.payments) || [];
            renderPaymentsSummary();
            renderPaymentsTable();
        }
    } catch (e) {
        console.error('Failed to fetch payments from API:', e);
    }
}

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

    if (!paymentsData.length) return;

    if (totalCount) totalCount.textContent = String(paymentsData.length);
    if (successfulCount) {
        successfulCount.textContent = String(paymentsData.filter(p => {
            const s = (p.payment_status || p.status || '').toLowerCase();
            return s === 'completed' || s === 'successful';
        }).length);
    }
    if (pendingCount) {
        pendingCount.textContent = String(paymentsData.filter(p => {
            const s = (p.payment_status || p.status || '').toLowerCase();
            return s === 'pending';
        }).length);
    }
    if (totalAmount) {
        const total = paymentsData
            .filter(p => {
                const s = (p.payment_status || p.status || '').toLowerCase();
                return s === 'completed' || s === 'successful';
            })
            .reduce((sum, p) => sum + (Number(p.amount_num != null ? p.amount_num : p.amount) || 0), 0);
        totalAmount.textContent = `₦ ${formatCurrency(total)}`;
    }
}

function renderPaymentsTable() {
    const tableBody = document.getElementById('paymentsTableBody');
    const emptyState = document.getElementById('paymentsEmptyState');
    const searchInput = document.getElementById('paymentsSearch');
    const statusFilter = document.getElementById('paymentsStatusFilter');
    const methodFilter = document.getElementById('paymentsMethodFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const statusValue = (statusFilter?.value || 'all').toLowerCase();
    const methodValue = (methodFilter?.value || 'all').toLowerCase();

    const filtered = paymentsData.filter(payment => {
        const ref = (payment.payment_reference || payment.reference || '').toLowerCase();
        const orderNo = (payment.order_number || payment.orderNumber || '').toLowerCase();
        const customer = (payment.customer_name || payment.customerName || (typeof payment.customer === 'string' ? payment.customer : '') || '').toLowerCase();
        const rawStatus = (payment.payment_status || payment.status || '').toLowerCase();
        const rawMethod = (payment.payment_method || payment.method || '').toLowerCase();

        const matchesQuery = !query || ref.includes(query) || orderNo.includes(query) || customer.includes(query);

        let matchesStatus = (statusValue === 'all');
        if (!matchesStatus) {
            if (statusValue === 'successful') {
                matchesStatus = rawStatus === 'completed' || rawStatus === 'successful';
            } else {
                matchesStatus = rawStatus.includes(statusValue);
            }
        }

        let matchesMethod = (methodValue === 'all');
        if (!matchesMethod) {
            if (methodValue === 'cash') {
                matchesMethod = rawMethod.includes('cash');
            } else if (methodValue === 'transfer') {
                matchesMethod = rawMethod.includes('transfer') || rawMethod.includes('qr') || rawMethod.includes('paystack');
            } else if (methodValue === 'card') {
                matchesMethod = rawMethod.includes('card') || rawMethod.includes('moniepoint') || rawMethod.includes('pos');
            } else if (methodValue === 'credit') {
                matchesMethod = rawMethod.includes('credit');
            } else {
                matchesMethod = rawMethod.includes(methodValue);
            }
        }

        return matchesQuery && matchesStatus && matchesMethod;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(payment => {
        const ref = payment.payment_reference || payment.reference || '-';
        const orderNum = payment.order_number || payment.orderNumber || '-';
        const cust = payment.customer_name || payment.customerName || (typeof payment.customer === 'string' ? payment.customer : '') || 'Walk-in Customer';
        const rawStatus = (payment.payment_status || payment.status || '').toLowerCase();
        const displayStatus = payment.status || payment.payment_status || 'Pending';
        const displayMethod = payment.method || payment.payment_method || 'Cash';
        const amountVal = payment.amount_num != null ? payment.amount_num : payment.amount;

        let statusClass = 'pending';
        if (rawStatus === 'completed' || rawStatus === 'successful') {
            statusClass = 'successful';
        } else if (rawStatus === 'failed') {
            statusClass = 'failed';
        } else if (rawStatus === 'refunded') {
            statusClass = 'refunded';
        }

        return `
            <tr>
                <td data-label="Reference">${escapeHtml(ref)}</td>
                <td data-label="Order #">${escapeHtml(orderNum)}</td>
                <td data-label="Customer">${escapeHtml(cust)}</td>
                <td data-label="Date">${formatDate(payment.created_at || payment.date)}</td>
                <td data-label="Amount" class="num">₦ ${formatCurrency(amountVal)}</td>
                <td data-label="Method"><span class="method-badge">${escapeHtml(displayMethod)}</span></td>
                <td data-label="Status"><span class="status-pill ${statusClass}">${escapeHtml(displayStatus)}</span></td>
                <td data-label="Action" style="text-align: right;"><a href="/payments/${encodeURIComponent(payment.id)}/" class="action-link">View</a></td>
            </tr>
        `;
    }).join('');
}

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
