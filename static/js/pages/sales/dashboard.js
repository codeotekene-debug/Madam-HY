document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('dashboardApplyBtn')?.addEventListener('click', loadDashboard);
    document.getElementById('dashboardClearBtn')?.addEventListener('click', () => {
        document.getElementById('dashboardDateFrom').value = '';
        document.getElementById('dashboardDateTo').value = '';
        loadDashboard();
    });
    document.getElementById('dashboardRetryBtn')?.addEventListener('click', loadDashboard);
    loadDashboard();
});

async function loadDashboard() {
    showDashboardError('');
    showDashboardEmpty(false);
    setDashboardLoading(true);
    const query = new URLSearchParams();
    const dateFrom = document.getElementById('dashboardDateFrom')?.value;
    const dateTo = document.getElementById('dashboardDateTo')?.value;
    if (dateFrom) query.set('date_from', dateFrom);
    if (dateTo) query.set('date_to', dateTo);
    const queryString = query.toString();
    const response = await apiRequest(`/sales/reports/summary/${queryString ? `?${queryString}` : ''}`);
    setDashboardLoading(false);
    if (!response.success) {
        showDashboardError(formatApiError(response));
        return;
    }
    const data = response.data || {};
    const hasSales = Number(data.transaction_count || 0) > 0;
    showDashboardEmpty(!hasSales);
    setText('dashboardTotalSales', `NGN ${formatCurrency(data.total_sales)}`);
    setText('dashboardTransactionCount', formatNumber(data.transaction_count));
    setText('dashboardTotalDiscount', `NGN ${formatCurrency(data.total_discount)}`);
    setText('dashboardCashTotal', `NGN ${formatCurrency(data.cash_total)}`);
    setText('dashboardTransferTotal', `NGN ${formatCurrency(data.transfer_total)}`);
    setText('dashboardCardTotal', `NGN ${formatCurrency(data.card_total)}`);
    setText('dashboardCreditTotal', `NGN ${formatCurrency(data.credit_total)}`);
}

function setDashboardLoading(loading) {
    ['dashboardTotalSales', 'dashboardTransactionCount', 'dashboardTotalDiscount', 'dashboardCashTotal', 'dashboardTransferTotal', 'dashboardCardTotal', 'dashboardCreditTotal'].forEach(id => {
        if (loading) setText(id, 'Loading...');
    });
}
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function showDashboardEmpty(show) { document.getElementById('dashboardEmptyState')?.classList.toggle('empty-state-hidden', !show); }
function showDashboardError(message) { const element = document.getElementById('dashboardErrorState'); if (element) { element.textContent = message; element.className = `card sale-message${message ? ' error' : ''}`; } }
function formatNumber(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Sales dashboard could not load.'); }
