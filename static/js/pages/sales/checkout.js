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
    document.getElementById('verifyCheckoutQrBtn')?.addEventListener('click', checkCheckoutQrStatus);
    document.getElementById('cancelCheckoutBtn')?.addEventListener('click', () => {
        sessionStorage.removeItem('madamHyDraftSale');
        window.location.href = '/sales/pos/';
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

    if (sale.payment_method === 'TRANSFER') {
        loadCheckoutQr(sale);
    }
}

let currentCheckoutQrRef = null;
let checkoutQrPollInterval = null;
let checkoutFallbackTimerInterval = null;

function bindFallbackCopyHandlers() {
    const copyAccBtn = document.getElementById('copyAccountNumberBtn');
    const accEl = document.getElementById('fallbackAccountNumber');
    if (copyAccBtn && accEl) {
        copyAccBtn.onclick = () => {
            navigator.clipboard.writeText(accEl.textContent.trim()).then(() => {
                copyAccBtn.innerHTML = '<i class="bi bi-check2"></i>';
                setTimeout(() => { copyAccBtn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 2000);
            });
        };
    }

    const copyLinkBtn = document.getElementById('copyPaymentLinkBtn');
    const linkEl = document.getElementById('qrPaymentLink');
    if (copyLinkBtn && linkEl) {
        copyLinkBtn.onclick = () => {
            navigator.clipboard.writeText(linkEl.href).then(() => {
                copyLinkBtn.innerHTML = '<i class="bi bi-check2"></i> Copied';
                setTimeout(() => { copyLinkBtn.innerHTML = '<i class="bi bi-link-45deg"></i> Copy'; }, 2000);
            });
        };
    }
}

function startCheckoutFallbackTimer() {
    if (checkoutFallbackTimerInterval) clearInterval(checkoutFallbackTimerInterval);
    const timerEl = document.getElementById('fallbackTimer');
    let remaining = 900;
    checkoutFallbackTimerInterval = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            clearInterval(checkoutFallbackTimerInterval);
            if (timerEl) timerEl.textContent = 'Expired';
            return;
        }
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        if (timerEl) {
            timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

async function loadCheckoutQr(sale) {
    const qrContainer = document.getElementById('checkoutQrContainer');
    const qrWrapper = document.getElementById('qrCodeWrapper');
    const qrStatusEl = document.getElementById('qrStatusText');
    const qrRefBadge = document.getElementById('qrReferenceBadge');
    const qrRefValue = document.getElementById('qrReferenceValue');

    if (!qrContainer || !qrWrapper || !sale) return;
    qrContainer.style.display = 'block';

    if (qrStatusEl) qrStatusEl.textContent = 'Generating dynamic payment QR code...';

    const qrRes = await apiRequest('/payments/qr/generate/', {
        method: 'POST',
        body: {
            sale_id: sale.id,
            target_type: 'sale',
            provider: 'paystack',
            amount: sale.total,
            format: 'png',
        },
    });

    if (!qrRes.success || !qrRes.data) {
        if (qrStatusEl) qrStatusEl.textContent = qrRes.message || 'Could not generate QR code.';
        qrWrapper.innerHTML = `<div class="qr-placeholder"><p>${escapeHtml(qrRes.message || 'QR generation failed.')}</p></div>`;
        return;
    }

    const qrData = qrRes.data;
    currentCheckoutQrRef = qrData.payment_reference;

    if (qrRefBadge && qrRefValue && currentCheckoutQrRef) {
        qrRefValue.textContent = currentCheckoutQrRef;
        qrRefBadge.style.display = 'inline-flex';
    }

    const src = qrData.qr_code_data || qrData.qr_code_png || qrData.qr_code_base64 || qrData.qr_code_data_uri || qrData.qr_data_uri || qrData.qr_code;
    const svg = qrData.qr_code_svg || qrData.qr_svg;
    if (src) {
        qrWrapper.innerHTML = `<img id="qrCodeImage" class="qr-code-img" src="${escapeHtml(src)}" alt="Payment QR Code" style="max-width: 100%; height: auto; padding: 10px; background: #ffffff; border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); display: block; margin: 0 auto;" />`;
    } else if (svg) {
        qrWrapper.innerHTML = `<div id="qrCodeContainer" class="qr-rendered-svg">${svg}</div>`;
    } else {
        qrWrapper.innerHTML = `<div class="qr-placeholder"><p>Scan to pay NGN ${formatCurrency(sale.total)}</p></div>`;
    }

    // Populate fallback details
    const fallbackRefEl = document.getElementById('fallbackRefValue');
    const fallbackBankEl = document.getElementById('fallbackBankName');
    const fallbackAccEl = document.getElementById('fallbackAccountNumber');
    const fallbackAmountEl = document.getElementById('fallbackAmount');
    const fallbackLinkEl = document.getElementById('qrPaymentLink');
    const fallbackLinkTextEl = document.getElementById('qrPaymentLinkText');

    if (fallbackRefEl) fallbackRefEl.textContent = qrData.payment_reference || currentCheckoutQrRef;
    if (fallbackBankEl) fallbackBankEl.textContent = qrData.bank_name || 'Moniepoint MFB';
    if (fallbackAccEl) fallbackAccEl.textContent = qrData.account_number || '-';
    if (fallbackAmountEl) fallbackAmountEl.textContent = `₦ ${formatCurrency(sale.total)}`;

    const payUrl = qrData.payment_url || qrData.checkout_url || qrData.qr_payload || '#';
    if (fallbackLinkEl) fallbackLinkEl.href = payUrl;
    if (fallbackLinkTextEl) fallbackLinkTextEl.textContent = payUrl;

    bindFallbackCopyHandlers();
    startCheckoutFallbackTimer();

    if (qrStatusEl) qrStatusEl.textContent = 'Awaiting customer transfer...';

    if (checkoutQrPollInterval) clearInterval(checkoutQrPollInterval);
    checkoutQrPollInterval = setInterval(checkCheckoutQrStatus, 3500);
}

async function checkCheckoutQrStatus() {
    if (!currentCheckoutQrRef || !draftState?.sale?.id) return;
    const qrStatusEl = document.getElementById('qrStatusText');
    const res = await apiRequest(`/payments/qr/${encodeURIComponent(currentCheckoutQrRef)}/status/`);
    if (!res.success) return;

    const data = res.data;
    const isCompleted = data.status === 'COMPLETED' || data.payment_status === 'COMPLETED' || data.is_verified === true;
    if (isCompleted) {
        if (checkoutQrPollInterval) {
            clearInterval(checkoutQrPollInterval);
            checkoutQrPollInterval = null;
        }
        if (qrStatusEl) qrStatusEl.textContent = 'Payment Confirmed! Finalizing sale...';
        showMessage('checkoutMessage', 'Payment confirmed via QR transfer! Finalizing...', 'success');
        window.setTimeout(() => {
            completeDraftSale();
        }, 1000);
    } else if (data.status === 'FAILED') {
        if (checkoutQrPollInterval) {
            clearInterval(checkoutQrPollInterval);
            checkoutQrPollInterval = null;
        }
        if (qrStatusEl) qrStatusEl.textContent = 'Payment Failed.';
        showMessage('checkoutMessage', 'Payment transaction failed or was declined.', 'error');
    } else if (data.status === 'EXPIRED') {
        if (checkoutQrPollInterval) {
            clearInterval(checkoutQrPollInterval);
            checkoutQrPollInterval = null;
        }
        if (qrStatusEl) qrStatusEl.textContent = 'Payment Expired.';
        showMessage('checkoutMessage', 'Payment request expired. Please regenerate QR.', 'warning');
    }
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
        window.location.href = `/sales/receipt/?sale_id=${response.data.sale_number}`;
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