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
    setText('totalSalesCount', pagination?.total_count ?? sales.length);
    setText('cashSalesCount', sales.filter(sale => sale.payment_method === 'CASH').length);
    setText('cardSalesCount', sales.filter(sale => sale.payment_method === 'CARD').length);
    setText('revenueTotal', `NGN ${formatCurrency(sales.reduce((sum, sale) => sum + Number(sale.total || 0), 0))}`);
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
            <td data-label="Sale #">${escapeHtml(sale.sale_number)}</td>
            <td data-label="Customer">${escapeHtml(sale.customer?.full_name || 'Walk-in customer')}</td>
            <td data-label="Cashier">${escapeHtml(sale.cashier?.full_name || sale.cashier?.username || '-')}</td>
            <td data-label="Date">${formatDate(sale.created_at)}</td>
            <td data-label="Payment">${escapeHtml(formatPaymentMethod(sale.payment_method))}</td>
            <td data-label="Status"><span class="status-pill ${String(sale.status).toLowerCase()}">${escapeHtml(formatStatus(sale.status))}</span></td>
            <td data-label="Total">NGN ${formatCurrency(sale.total)}</td>
            <td data-label="Action"><a href="/preview/sales/detail/?sale_id=${sale.id}" class="action-link">View</a></td>
        </tr>
    `).join('');
}

function renderPagination(pagination) {
    const container = document.getElementById('historyPagination');
    if (!container || !pagination || pagination.total_pages <= 1) {
        if (container) container.innerHTML = '';
        return;
    }
    container.innerHTML = `
        <button type="button" class="btn btn-secondary" data-page="${Math.max(1, pagination.page - 1)}" ${pagination.page <= 1 ? 'disabled' : ''}>Previous</button>
        <span>Page ${pagination.page} of ${pagination.total_pages}</span>
        <button type="button" class="btn btn-secondary" data-page="${Math.min(pagination.total_pages, pagination.page + 1)}" ${pagination.page >= pagination.total_pages ? 'disabled' : ''}>Next</button>
    `;
    container.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
        salesHistoryState.page = Number(button.dataset.page);
        loadSalesHistory();
    }));
}

function showHistoryEmpty(show) { document.getElementById('historyEmptyState')?.classList.toggle('empty-state-hidden', !show); }
function showHistoryError(message) { const element = document.getElementById('historyErrorState'); if (element) { element.textContent = message; element.className = `sale-message${message ? ' error' : ''}`; } }
function loadingRow(message) { return `<tr><td colspan="8">${escapeHtml(message)}</td></tr>`; }
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function formatPaymentMethod(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatStatus(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatDate(value) { if (!value) return '-'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '-' : date.toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' }); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Sales history could not load.'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }
function debounce(callback, delay) { let timer; return (...args) => { window.clearTimeout(timer); timer = window.setTimeout(() => callback(...args), delay); }; }
