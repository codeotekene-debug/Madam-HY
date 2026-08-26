/** MADAM HY - Customer Cart */

window.madamHyCart = window.madamHyCart || [];
const cartItems = window.madamHyCart;

document.addEventListener('DOMContentLoaded', () => {
    renderCart();
    document.getElementById('checkoutBtn')?.addEventListener('click', () => {
        if (!cartItems.length) {
            showCartMessage('Your cart is empty.');
            return;
        }
        window.location.href = '/customer/checkout/';
    });
});

function renderCart() {
    const list = document.getElementById('cartItemsList');
    const empty = document.getElementById('cartEmptyState');
    if (!list) return;
    if (!cartItems.length) {
        list.replaceChildren();
        empty?.classList.remove('empty-state-hidden');
        updateSummary();
        updateCartCount();
        return;
    }
    empty?.classList.add('empty-state-hidden');
    list.innerHTML = cartItems.map(item => `
        <div class="cart-item">
            <div class="cart-item-image"><img src="${escapeHtml(item.image || '')}" alt="${escapeHtml(item.name)}" /></div>
            <div class="cart-item-details">
                <div class="cart-item-name">${escapeHtml(item.name)}</div>
                <div class="cart-item-price">₦${formatCurrency(item.price)}</div>
                <label>Quantity <input class="form-control" type="number" min="1" value="${item.quantity}" data-cart-quantity="${item.id}" /></label>
            </div>
            <div class="cart-item-actions"><button type="button" class="cart-remove-btn" data-remove-cart-item="${item.id}">Remove</button></div>
        </div>
    `).join('');
    list.querySelectorAll('[data-remove-cart-item]').forEach(button => button.addEventListener('click', () => {
        const index = cartItems.findIndex(item => String(item.id) === button.dataset.removeCartItem);
        if (index >= 0) cartItems.splice(index, 1);
        renderCart();
    }));
    list.querySelectorAll('[data-cart-quantity]').forEach(input => input.addEventListener('change', () => {
        const item = cartItems.find(entry => String(entry.id) === input.dataset.cartQuantity);
        const quantity = Number.parseInt(input.value, 10);
        if (item) item.quantity = Number.isInteger(quantity) && quantity > 0 ? quantity : 1;
        renderCart();
    }));
    updateSummary();
    updateCartCount();
}

function updateCartCount() {
    const count = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('cartItemsCount')?.replaceChildren(document.createTextNode(`${count} ${count === 1 ? 'item' : 'items'} in your cart`));
}

function updateSummary() {
    const subtotal = cartItems.reduce((sum, item) => sum + item.price * item.quantity, 0);
    document.getElementById('cartSubtotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
    document.getElementById('cartTax')?.replaceChildren(document.createTextNode('Calculated by the shop'));
    document.getElementById('cartTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
}

function showCartMessage(message) {
    const empty = document.getElementById('cartEmptyState');
    empty?.querySelector('p')?.replaceChildren(document.createTextNode(message));
    empty?.classList.remove('empty-state-hidden');
}

function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG'); }
function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}