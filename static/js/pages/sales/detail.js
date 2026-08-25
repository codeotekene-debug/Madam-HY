document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('detailRetryBtn')?.addEventListener('click', loadSaleDetail);
    loadSaleDetail();
});

async function loadSaleDetail() {
    const saleId = new URLSearchParams(window.location.search).get('sale_id');
    if (!saleId) {
        showMessage('Sale ID is missing.', 'error');
        return;
    }
    showMessage('Loading sale detail...', '');
    const response = await apiRequest(`/sales/${encodeURIComponent(saleId)}/`);
    if (!response.success) {
        showMessage(formatApiError(response), 'error');
        return;
    }
    const sale = response.data;
    setText('detailSaleNumber', `Sale #${sale.sale_number}`);
    setText('detailDate', formatDate(sale.created_at));
    setText('detailStatus', formatStatus(sale.status));
    const statusElement = document.getElementById('detailStatus');
    if (statusElement) statusElement.className = `status-pill ${String(sale.status).toLowerCase()}`;
    setText('detailCustomer', sale.customer?.full_name || 'Walk-in customer');
    setText('detailCashier', sale.cashier?.full_name || sale.cashier?.username || '-');
    setText('detailPayment', formatPaymentMethod(sale.payment_method));
    setText('detailPaymentStatus', formatStatus(sale.payment_status));
    setText('detailSubtotal', `NGN ${formatCurrency(sale.subtotal)}`);
    setText('detailDiscount', `NGN ${formatCurrency(sale.discount)}`);
    setText('detailTotal', `NGN ${formatCurrency(sale.total)}`);
    setText('detailAmountReceived', sale.amount_received == null ? '-' : `NGN ${formatCurrency(sale.amount_received)}`);
    setText('detailChange', sale.change_amount == null ? '-' : `NGN ${formatCurrency(sale.change_amount)}`);
    const body = document.getElementById('detailItemsBody');
    if (body) body.innerHTML = (sale.items || []).map(item => `
        <tr><td>${escapeHtml(item.product_name_snapshot)}</td><td>${item.quantity}</td><td>NGN ${formatCurrency(item.unit_price)}</td><td>NGN ${formatCurrency(item.line_total)}</td></tr>
    `).join('');
    showMessage('', '');
}

function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function showMessage(message, type) { const element = document.getElementById('detailMessage'); if (element) { element.textContent = message; element.className = `sale-message${type ? ` ${type}` : ''}`; } }
function formatPaymentMethod(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatStatus(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatDate(value) { if (!value) return '-'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('en-NG'); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Sale detail could not load.'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }
