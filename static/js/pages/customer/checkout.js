/**
 * MADAM HY - Customer Cart
 * Frontend-only shopping cart management
 */

let cartItems = [
    { id: 1, name: "Green Ankara Fabric Premium", price: 12500, quantity: 2, image: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=900&q=80" },
    { id: 3, name: "Radiant Glow Serum", price: 9500, quantity: 1, image: "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=900&q=80" }
];

const TAX_RATE = 0.075;

document.addEventListener('DOMContentLoaded', () => {
    renderCart();
    bindCartActions();
});

function renderCart() {
    const itemsList = document.getElementById('cartItemsList');
    const emptyState = document.getElementById('cartEmptyState');

    if (!itemsList) return;

    if (cartItems.length === 0) {
        itemsList.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        updateSummary();
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    itemsList.innerHTML = cartItems.map(item => `
        <div class="cart-item">
            <div class="cart-item-image">
                <img src="${item.image}" alt="${item.name}" />
            </div>
            <div class="cart-item-details">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-price">₦${formatCurrency(item.price)}</div>
            </div>
            <div class="cart-item-actions">
                <button type="button" class="cart-remove-btn" onclick="removeFromCart(${item.id})">Remove</button>
            </div>
        </div>
    `).join('');

    updateSummary();
    updateCartCount();
}

function removeFromCart(id) {
    cartItems = cartItems.filter(item => item.id !== id);
    renderCart();
}

function updateCartCount() {
    const count = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    const itemsText = count === 1 ? 'item' : 'items';
    document.getElementById('cartItemsCount')?.replaceChildren(document.createTextNode(`${count} ${itemsText} in your cart`));
}

function updateSummary() {
    const subtotal = cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    const tax = Math.round(subtotal * TAX_RATE);
    const total = subtotal + tax;

    document.getElementById('cartSubtotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(subtotal)}`));
    document.getElementById('cartTax')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(tax)}`));
    document.getElementById('cartTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));
}

function bindCartActions() {
    const checkoutBtn = document.getElementById('checkoutBtn');
    checkoutBtn?.addEventListener('click', () => {
        if (cartItems.length === 0) {
            alert('Your cart is empty!');
            return;
        }
        window.location.href = '/customer/checkout/';
    });
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
