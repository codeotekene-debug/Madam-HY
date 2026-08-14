document.addEventListener('DOMContentLoaded', () => {
    const receipt = JSON.parse(localStorage.getItem('madamHyReceipt') || 'null');
    const summary = document.getElementById('checkoutItems');
    const subtotal = document.getElementById('checkoutSubtotal');
    const discount = document.getElementById('checkoutDiscount');
    const total = document.getElementById('checkoutTotal');
    const change = document.getElementById('checkoutChange');
    const amountReceivedInput = document.getElementById('amountReceivedInput');
    const paymentMethodSelect = document.getElementById('paymentMethodSelect');
    const customerName = document.getElementById('customerName');
    const customerPhone = document.getElementById('customerPhone');
    const confirmPaymentBtn = document.getElementById('confirmPaymentBtn');
    const cancelCheckoutBtn = document.getElementById('cancelCheckoutBtn');

    if (receipt) {
        if (summary) {
            summary.innerHTML = receipt.items.map(item => `
                <li>
                    <span>${item.name} x${item.qty}</span>
                    <strong>₦ ${formatCurrency(item.total)}</strong>
                </li>
            `).join('');
        }

        if (subtotal) subtotal.textContent = `₦ ${formatCurrency(receipt.subtotal)}`;
        if (discount) discount.textContent = `₦ ${formatCurrency(receipt.discount)}`;
        if (total) total.textContent = `₦ ${formatCurrency(receipt.total)}`;
        if (change) change.textContent = `₦ ${formatCurrency(receipt.change)}`;
        if (amountReceivedInput) amountReceivedInput.value = String(receipt.total);
        if (paymentMethodSelect) paymentMethodSelect.value = receipt.payment;
    }

    paymentMethodSelect?.addEventListener('change', () => updateCheckoutSummary());
    amountReceivedInput?.addEventListener('input', updateCheckoutSummary);

    function updateCheckoutSummary() {
        const subtotalValue = Number(receipt?.subtotal || 0);
        const discountValue = Number(receipt?.discount || 0);
        const totalValue = Math.max(subtotalValue - discountValue, 0);
        const amountReceived = Number(amountReceivedInput?.value || 0);
        const calculatedChange = Math.max(amountReceived - totalValue, 0);

        if (subtotal) subtotal.textContent = `₦ ${formatCurrency(subtotalValue)}`;
        if (discount) discount.textContent = `₦ ${formatCurrency(discountValue)}`;
        if (total) total.textContent = `₦ ${formatCurrency(totalValue)}`;
        if (change) change.textContent = `₦ ${formatCurrency(calculatedChange)}`;
    }

    confirmPaymentBtn?.addEventListener('click', () => {
        const message = document.getElementById('checkoutMessage');
        const payable = Number(receipt?.total || 0);
        const amount = Number(amountReceivedInput?.value || 0);

        if (!customerName?.value.trim()) {
            showMessage(message, 'Customer name is required before confirming payment.', 'error');
            return;
        }

        if (amount < payable) {
            showMessage(message, 'Amount received is lower than the total due.', 'error');
            return;
        }

        const finalReceipt = {
            ...receipt,
            customer: customerName.value.trim(),
            phone: customerPhone?.value.trim() || 'N/A',
            payment: paymentMethodSelect?.value || 'Cash',
            amountReceived: amount,
            change: Math.max(amount - payable, 0),
            number: receipt?.number || `MH-${String(Date.now()).slice(-6)}`,
            date: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
        };

        localStorage.setItem('madamHyReceipt', JSON.stringify(finalReceipt));
        showMessage(message, 'Payment confirmed. Receipt generated.', 'success');
        setTimeout(() => {
            window.location.href = '/sales/receipt/';
        }, 800);
    });

    cancelCheckoutBtn?.addEventListener('click', () => {
        window.location.href = '/sales/pos/';
    });

    function showMessage(element, message, type) {
        if (!element) return;
        element.textContent = message;
        element.className = `sale-message ${type}`;
        window.clearTimeout(showMessage.timeoutId);
        showMessage.timeoutId = window.setTimeout(() => {
            element.textContent = '';
            element.className = 'sale-message';
        }, 2600);
    }
});

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
