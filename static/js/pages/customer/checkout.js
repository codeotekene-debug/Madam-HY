/** MADAM HY - Customer Checkout */

window.madamHyCart = window.madamHyCart || [];
const checkoutCart = window.madamHyCart;

document.addEventListener('DOMContentLoaded', () => {
    renderCheckoutSummary();
    document.getElementById('checkoutForm')?.addEventListener('submit', submitOrder);
});

async function submitOrder(event) {
    event.preventDefault();
    const button = event.currentTarget.querySelector('button[type="submit"]');
    if (!checkoutCart.length) {
        showCheckoutError('Your cart is empty. Add products before placing an order.');
        return;
    }
    if (button) {
        button.disabled = true;
        button.textContent = 'Placing order...';
    }
    hideCheckoutError();
    const paymentMethod = document.querySelector('input[name="paymentMethod"]:checked')?.value || 'CASH';
    const notes = [
        document.getElementById('checkoutAddress')?.value.trim(),
        document.getElementById('checkoutDeliveryType')?.value,
        document.getElementById('checkoutPhone')?.value.trim(),
    ].filter(Boolean).join(' | ');
    const response = await apiRequest('/orders/', {
        method: 'POST',
        body: {
            items: checkoutCart.map(item => ({ product_id: item.id, quantity: item.quantity })),
            payment_method: paymentMethod,
            notes,
        },
    });
    if (!response.success) {
        showCheckoutError(response.message || 'Unable to place your order.');
        if (button) {
            button.disabled = false;
            button.textContent = 'Place order';
        }
        return;
    }
    checkoutCart.splice(0, checkoutCart.length);
    const order = response.data?.order;
    window.location.href = order ? `/preview/customer/order-detail/?id=${encodeURIComponent(order.id)}` : '/preview/customer/orders/';
}

function renderCheckoutSummary() {
    const list = document.getElementById('checkoutItemsList');
    if (!list) return;
    if (!checkoutCart.length) {
        list.replaceChildren(document.createTextNode('Your cart is empty.'));
    } else {
        list.innerHTML = checkoutCart.map(item => `<div class="checkout-item"><span>${escapeHtml(item.name)} × ${item.quantity}</span><strong>₦${formatCurrency(item.price * item.quantity)}</strong></div>`).join('');
    }
    const subtotal = checkoutCart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    document.getElementById('checkoutSubtotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
    document.getElementById('checkoutTax')?.replaceChildren(document.createTextNode('Calculated by the shop'));
    document.getElementById('checkoutDelivery')?.replaceChildren(document.createTextNode('Confirmed by the shop'));
    document.getElementById('checkoutTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
}

function showCheckoutError(message) {
    const target = document.getElementById('checkoutFormError');
    if (target) {
        target.textContent = message;
        target.classList.remove('hidden');
    }
}
function hideCheckoutError() { document.getElementById('checkoutFormError')?.classList.add('hidden'); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG'); }
function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}