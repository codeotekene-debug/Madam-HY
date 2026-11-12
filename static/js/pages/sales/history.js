const salesHistoryState = { page: 1, pageSize: 10 };

document.addEventListener('DOMContentLoaded', () => {
    bindHistoryFilters();
    loadSalesHistory();
});

function bindHistoryFilters() {
    document.getElementById('historySearch')?.addEventListener('input', debounce(() => {
        salesHistoryState.page = 1;
        loadSalesHistory();
    }, 250));

    ['historyPaymentFilter', 'historyStatusFilter', 'historyPaymentStatusFilter', 'historyDateFrom', 'historyDateTo'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', () => {
            salesHistoryState.page = 1;
            loadSalesHistory();
        });
    });

    document.getElementById('historyRetryBtn')?.addEventListener('click', loadSalesHistory);
}

async function loadSalesHistory() {
    const tableBody = document.getElementById('historyTableBody');
    if (!tableBody) return;
    showHistoryError('');
    showHistoryEmpty(false);
    tableBody.innerHTML = loadingRow('Loading sales history...');

    const query = new URLSearchParams({ page: String(salesHistoryState.page), page_size: String(salesHistoryState.pageSize) });
    const search = document.getElementById('historySearch')?.value.trim();
    const payment = document.getElementById('historyPaymentFilter')?.value;
    const status = document.getElementById('historyStatusFilter')?.value;
    const paymentStatus = document.getElementById('historyPaymentStatusFilter')?.value;
    const dateFrom = document.getElementById('historyDateFrom')?.value;
    const dateTo = document.getElementById('historyDateTo')?.value;

    if (search) query.set('search', search);
    if (payment && payment !== 'all') query.set('payment_method', payment);
    if (status && status !== 'all') query.set('status', status);
    if (paymentStatus && paymentStatus !== 'all') query.set('payment_status', paymentStatus);
    if (dateFrom) query.set('date_from', dateFrom);
    if (dateTo) query.set('date_to', dateTo);

    const response = await apiRequest(`/sales/?${query.toString()}`);
    if (!response.success) {
        tableBody.innerHTML = '';
        renderPagination(null);
        showHistoryError(formatApiError(response));
        return;
    }
    const sales = response.data?.sales || [];
    renderSalesSummary(sales, response.data?.pagination);
    renderSalesTable(sales);
    renderPagination(response.data?.pagination);
}

function renderSalesSummary(sales, pagination) {
    const totalCount = pagination?.total_count ?? sales.length;
    setText('totalSalesCount', totalCount.toLocaleString('en-NG'));
    setText('cashSalesCount', sales.filter(s => s.payment_method === 'CASH').length.toLocaleString('en-NG'));
    setText('cardSalesCount', sales.filter(s => s.payment_method === 'CARD').length.toLocaleString('en-NG'));
    const revenue = sales.reduce((sum, s) => sum + Number(s.total || 0), 0);
    setText('revenueTotal', `₦ ${formatCurrency(revenue)}`);
}

function renderSalesTable(sales) {
    const tableBody = document.getElementById('historyTableBody');
    if (!tableBody) return;

    if (!sales.length) {
        tableBody.innerHTML = '';
        showHistoryEmpty(true);
        return;
    }

    showHistoryEmpty(false);
    tableBody.innerHTML = sales.map(sale => `
        <tr>
            <td data-label="Sale # / Receipt">
                <strong style="color: var(--text-heading, #090d16); font-family: monospace;">${escapeHtml(sale.sale_number)}</strong>
            </td>
            <td data-label="Customer">
                <span class="customer-name">${escapeHtml(sale.customer?.full_name || 'Walk-in customer')}</span>
            </td>
            <td data-label="Cashier">
                <span class="cashier-name">${escapeHtml(sale.cashier?.full_name || sale.cashier?.username || '-')}</span>
            </td>
            <td data-label="Date & Time">
                <span class="date-text">${formatDate(sale.created_at)}</span>
            </td>
            <td data-label="Payment Channel">
                ${renderPaymentBadge(sale.payment_method)}
            </td>
            <td data-label="Status">
                ${renderStatusBadge(sale.status)}
            </td>
            <td data-label="Amount">
                <strong style="color: var(--text-heading, #090d16); font-size: 13.5px;">₦ ${formatCurrency(sale.total)}</strong>
            </td>
            <td data-label="Actions" style="text-align: right;">
                <div class="sales-actions-cell">
                    <a href="/sales/receipt/?sale_id=${sale.id}" class="btn-action btn-action-primary" title="View customer receipt">
                        <i class="bi bi-receipt" aria-hidden="true"></i>
                        <span>Receipt</span>
                    </a>
                    <button type="button" class="btn-action" data-print-sale="${sale.id}" title="Print receipt">
                        <i class="bi bi-printer" aria-hidden="true"></i>
                        <span>Print</span>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');

    tableBody.querySelectorAll('[data-print-sale]').forEach(btn => {
        btn.addEventListener('click', () => {
            const saleId = btn.dataset.printSale;
            const printWindow = window.open(`/sales/receipt/?sale_id=${saleId}&print=1`, '_blank');
            if (printWindow) {
                printWindow.focus();
            }
        });
    });
}

function renderPaymentBadge(method) {
    const raw = String(method || '').toUpperCase();
    switch (raw) {
        case 'CASH':
            return `<span class="pay-badge pay-cash"><i class="bi bi-cash-stack" aria-hidden="true"></i> Cash</span>`;
        case 'TRANSFER':
        case 'QR_CODE':
            return `<span class="pay-badge pay-transfer"><svg class="retail-svg icon-xs" aria-hidden="true"><use href="#icon-retail-qr"></use></svg> Dynamic QR</span>`;
        case 'CARD':
        case 'POS':
            return `<span class="pay-badge pay-pos"><svg class="retail-svg icon-xs" aria-hidden="true"><use href="#icon-retail-pos"></use></svg> Moniepoint POS</span>`;
        case 'CREDIT':
            return `<span class="pay-badge pay-credit"><svg class="retail-svg icon-xs" aria-hidden="true"><use href="#icon-retail-credit"></use></svg> Credit</span>`;
        default:
            return `<span class="pay-badge pay-cash">${escapeHtml(raw || '-')}</span>`;
    }
}

function renderStatusBadge(status) {
    const raw = String(status || '').toUpperCase();
    switch (raw) {
        case 'COMPLETED':
            return `<span class="status-pill completed"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> Completed</span>`;
        case 'REFUNDED':
            return `<span class="status-pill refunded"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i> Refunded</span>`;
        case 'PARTIALLY_REFUNDED':
            return `<span class="status-pill partially-refunded"><i class="bi bi-dash-circle-fill" aria-hidden="true"></i> Partial Refund</span>`;
        case 'DRAFT':
            return `<span class="status-pill draft"><i class="bi bi-hourglass-split" aria-hidden="true"></i> Draft</span>`;
        case 'CANCELLED':
            return `<span class="status-pill cancelled"><i class="bi bi-x-circle-fill" aria-hidden="true"></i> Cancelled</span>`;
        default:
            return `<span class="status-pill completed">${escapeHtml(raw)}</span>`;
    }
}

function renderPagination(pagination) {
    const container = document.getElementById('historyPagination');
    if (!container || !pagination || pagination.total_pages <= 1) {
        if (container) container.innerHTML = '';
        return;
    }
    container.innerHTML = `
        <button type="button" class="btn btn-secondary" data-page="${Math.max(1, pagination.page - 1)}" ${pagination.page <= 1 ? 'disabled' : ''}>
            <i class="bi bi-chevron-left" aria-hidden="true"></i> Previous
        </button>
        <span style="font-size: 13px; font-weight: 700; color: var(--text-secondary);">Page ${pagination.page} of ${pagination.total_pages}</span>
        <button type="button" class="btn btn-secondary" data-page="${Math.min(pagination.total_pages, pagination.page + 1)}" ${pagination.page >= pagination.total_pages ? 'disabled' : ''}>
            Next <i class="bi bi-chevron-right" aria-hidden="true"></i>
        </button>
    `;
    container.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
        salesHistoryState.page = Number(button.dataset.page);
        loadSalesHistory();
    }));
}

function showHistoryEmpty(show) { document.getElementById('historyEmptyState')?.classList.toggle('empty-state-hidden', !show); }
function showHistoryError(message) { const element = document.getElementById('historyErrorState'); if (element) { element.textContent = message; element.className = `sale-message${message ? ' error' : ''}`; } }
function loadingRow(message) { return `<tr><td colspan="8" style="text-align: center; padding: 30px;"><div class="dashboard-loading"><div class="spinner"></div><span>${escapeHtml(message)}</span></div></td></tr>`; }
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function formatDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Sales history could not load.'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }
function debounce(callback, delay) { let timer; return (...args) => { window.clearTimeout(timer); timer = window.setTimeout(() => callback(...args), delay); }; }
