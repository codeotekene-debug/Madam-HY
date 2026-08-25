let draftState = null;

document.addEventListener('DOMContentLoaded', () => {
    draftState = readSessionValue('madamHyDraftSale');
    bindCheckoutEvents();
    renderDraftSale();
});

function bindCheckoutEvents() {
    document.getElementById('paymentMethodSelect')?.addEventListener('change', updateCheckoutSummary);
    document.getElementById('amountReceivedInput')?.addEventListener('input', updateCheckoutSummary);
    document.getElementById('confirmPaymentBtn')?.addEventListener('click', completeDraftSale);
    document.getElementById('cancelCheckoutBtn')?.addEventListener('click', () => {
        sessionStorage.removeItem('madamHyDraftSale');
        window.location.href = '/preview/sales/pos/';
    });
}

function renderDraftSale() {
    const sale = draftState?.sale;
    if (!sale) {
        showMessage('checkoutMessage', 'This checkout session is no longer available.', 'error');
        setButtonDisabled('confirmPaymentBtn', true);
        return;
    }

    const items = draftState.items || sale.items || [];
    const summary = document.getElementById('checkoutItems');
    if (summary) {
        summary.innerHTML = items.map(item => `
            <li><span>${escapeHtml(item.product_name || item.product?.name || 'Product')} x${item.quantity}</span><strong>NGN ${formatCurrency(item.line_total)}</strong></li>
        `).join('');
    }
    setText('checkoutSubtotal', `NGN ${formatCurrency(sale.subtotal)}`);
    setText('checkoutDiscount', `NGN ${formatCurrency(sale.discount)}`);
    setText('checkoutTotal', `NGN ${formatCurrency(sale.total)}`);
    setText('customerName', sale.customer?.full_name || 'Walk-in customer', true);
    setText('customerPhone', sale.customer?.email || 'N/A', true);
    setInputValue('customerIdInput', sale.customer?.id || '');
    setInputValue('paymentMethodSelect', sale.payment_method || 'CASH');
    setInputValue('amountReceivedInput', sale.total || '0.00');
    setButtonDisabled('paymentMethodSelect', true);
    setButtonDisabled('customerIdInput', true);
    updateCheckoutSummary();
}

function updateCheckoutSummary() {
    const sale = draftState?.sale;
    if (!sale) return;
    const amount = Math.max(Number(document.getElementById('amountReceivedInput')?.value || 0), 0);
    const change = sale.payment_method === 'CASH' ? Math.max(amount - Number(sale.total || 0), 0) : 0;
    setText('checkoutChange', `NGN ${formatCurrency(change)}`);
    const amountInput = document.getElementById('amountReceivedInput');
    if (amountInput) amountInput.disabled = sale.payment_method !== 'CASH';
}

async function completeDraftSale() {
    const sale = draftState?.sale;
    if (!sale?.id) {
        showMessage('checkoutMessage', 'This checkout session is no longer available.', 'error');
        return;
    }
    const amount = Math.max(Number(document.getElementById('amountReceivedInput')?.value || 0), 0);
    if (sale.payment_method === 'CREDIT' && !sale.customer?.id) {
        showMessage('checkoutMessage', 'A customer is required for credit sales.', 'error');
        return;
    }

    const button = document.getElementById('confirmPaymentBtn');
    setButtonLoading(button, 'Completing sale...');
    const paymentBody = sale.payment_method === 'CASH'
        ? { amount_received: amount.toFixed(2) }
        : {};
    const response = await apiRequest(`/sales/${sale.id}/complete/`, { method: 'POST', body: paymentBody });
    setButtonLoading(button, 'Confirm payment');
    if (!response.success) {
        showMessage('checkoutMessage', formatApiError(response), 'error');
        return;
    }
    sessionStorage.setItem('madamHyCompletedSale', JSON.stringify(response.data));
    sessionStorage.removeItem('madamHyDraftSale');
    showMessage('checkoutMessage', response.message || 'Sale completed successfully.', 'success');
    window.setTimeout(() => {
        window.location.href = `/preview/sales/receipt/?sale_id=${response.data.sale_number}`;
    }, 500);
}

function readSessionValue(key) {
    try { return JSON.parse(sessionStorage.getItem(key) || 'null'); }
    catch (error) { return null; }
}

function setText(id, value, input = false) {
    const element = document.getElementById(id);
    if (element) input ? element.value = value : element.textContent = value;
}
function setInputValue(id, value) { const element = document.getElementById(id); if (element) element.value = value; }
function setButtonDisabled(id, disabled) { const element = document.getElementById(id); if (element) element.disabled = disabled; }
function setButtonLoading(button, label) { if (button) { button.disabled = label !== 'Confirm payment'; button.textContent = label; } }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Request failed.'); }
function showMessage(id, message, type) { const element = document.getElementById(id); if (element) { element.textContent = message; element.className = `sale-message ${type}`; } }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }