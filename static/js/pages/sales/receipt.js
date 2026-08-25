document.addEventListener('DOMContentLoaded', () => {
    const sale = readSessionValue('madamHyCompletedSale');
    if (!sale) {
        setText('receiptNumber', 'N/A');
        setText('receiptDate', 'No completed sale found');
        return;
    }

    setText('receiptNumber', sale.sale_number || 'N/A');
    setText('receiptDate', formatDate(sale.completed_at));
    setText('receiptCashier', sale.customer?.full_name || 'Walk-in customer');
    setText('receiptSubtotal', `NGN ${formatCurrency(sale.subtotal)}`);
    setText('receiptDiscount', `NGN ${formatCurrency(sale.discount)}`);
    setText('receiptTotal', `NGN ${formatCurrency(sale.total)}`);
    setText('receiptPayment', formatPaymentMethod(sale.payment_method));
    setText('receiptChange', `NGN ${formatCurrency(sale.change_amount)}`);

    const itemTable = document.getElementById('receiptItems');
    if (itemTable) {
        itemTable.innerHTML = (sale.items || []).map(item => `
            <tr><td>${escapeHtml(item.product_name || 'Product')}</td><td>${item.quantity}</td><td>NGN ${formatCurrency(item.line_total)}</td></tr>
        `).join('');
    }
});

function readSessionValue(key) {
    try { return JSON.parse(sessionStorage.getItem(key) || 'null'); }
    catch (error) { return null; }
}
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function formatPaymentMethod(value) { return String(value || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatDate(value) { if (!value) return 'N/A'; const date = new Date(value); return Number.isNaN(date.getTime()) ? 'N/A' : date.toLocaleString('en-NG'); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }