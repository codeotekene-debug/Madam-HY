document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('receiptRetryBtn')?.addEventListener('click', loadReceipt);
    loadReceipt();
});

async function loadReceipt() {
    const identifier = new URLSearchParams(window.location.search).get('sale_id');
    if (!identifier) {
        showReceiptMessage('Sale number is missing.');
        return;
    }

    let saleId = identifier;
    if (!/^\d+$/.test(identifier)) {
        const listResponse = await apiRequest(`/sales/?search=${encodeURIComponent(identifier)}&page_size=1`);
        if (!listResponse.success || !listResponse.data?.sales?.length) {
            showReceiptMessage(formatApiError(listResponse));
            return;
        }
        saleId = listResponse.data.sales[0].id;
    }

    const response = await apiRequest(`/sales/${encodeURIComponent(saleId)}/`);
    if (!response.success) {
        showReceiptMessage(formatApiError(response));
        return;
    }
    renderReceipt(response.data);
}

function renderReceipt(sale) {
    setText('receiptNumber', sale.sale_number || 'N/A');
    setText('receiptDate', formatDate(sale.created_at));
    setText('receiptCashier', sale.cashier?.full_name || sale.cashier?.username || '-');
    setText('receiptSubtotal', `NGN ${formatCurrency(sale.subtotal)}`);
    setText('receiptDiscount', `NGN ${formatCurrency(sale.discount)}`);
    setText('receiptTotal', `NGN ${formatCurrency(sale.total)}`);
    setText('receiptPayment', formatPaymentMethod(sale.payment_method));
    setText('receiptPaymentStatus', formatStatus(sale.payment_status));
    setText('receiptAmountReceived', sale.amount_received == null ? '-' : `NGN ${formatCurrency(sale.amount_received)}`);
    setText('receiptChange', sale.change_amount == null ? '-' : `NGN ${formatCurrency(sale.change_amount)}`);
    const itemTable = document.getElementById('receiptItems');
    if (itemTable) {
        itemTable.innerHTML = (sale.items || []).map(item => `
            <tr><td>${escapeHtml(item.product_name_snapshot)}</td><td>${item.quantity}</td><td>NGN ${formatCurrency(item.line_total)}</td></tr>
        `).join('');
    }
}

function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function showReceiptMessage(message) { setText('receiptDate', message); }
function formatPaymentMethod(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatStatus(value) { return String(value || '-').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatDate(value) { if (!value) return '-'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('en-NG'); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Receipt could not load.'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }
