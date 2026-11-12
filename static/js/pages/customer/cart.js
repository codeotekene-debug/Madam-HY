/**
 * MADAM HY - Customer Cart Controller
 */

let currentCartData = { items: [], subtotal: '0.00', total: '0.00', item_count: 0 };


document.addEventListener('DOMContentLoaded', () => {
    loadAndRenderCart();

    document.getElementById('checkoutBtn')?.addEventListener('click', () => {
        if (!currentCartData.items || !currentCartData.items.length) {
            alert('Your cart is empty. Add items to proceed.');
            return;
        }
        window.location.href = '/customer/checkout/';
    });

    document.getElementById('clearCartBtn')?.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to clear your shopping bag?')) return;
        const response = await apiRequest('/customer/cart/items/', {
            method: 'DELETE',
        });
        if (response.success) {
            currentCartData = response.data || { items: [], subtotal: '0.00', total: '0.00', item_count: 0 };
            renderCart();
        }
    });
});

async function loadAndRenderCart() {
    const list = document.getElementById('cartItemsList');
    const empty = document.getElementById('cartEmptyState');
    if (!list) return;

    const response = await apiRequest('/customer/cart/?format=json');
    if (!response.success) {
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            return;
        }
        return;
    }

    currentCartData = response.data || { items: [], subtotal: '0.00', total: '0.00', item_count: 0 };
    renderCart();
}

function renderCart() {
    const list = document.getElementById('cartItemsList');
    const empty = document.getElementById('cartEmptyState');
    if (!list) return;

    const items = currentCartData.items || [];

    if (!items.length) {
        list.replaceChildren();
        empty?.classList.remove('empty-state-hidden');
        updateSummary();

        updateHeaderBadge(0);
        const checkoutBtn = document.getElementById('checkoutBtn');
        if (checkoutBtn) checkoutBtn.disabled = true;
        const clearBtn = document.getElementById('clearCartBtn');
        if (clearBtn) clearBtn.disabled = true;
        return;
    }

    empty?.classList.add('empty-state-hidden');
    const checkoutBtn = document.getElementById('checkoutBtn');
    if (checkoutBtn) checkoutBtn.disabled = false;
    const clearBtn = document.getElementById('clearCartBtn');
    if (clearBtn) clearBtn.disabled = false;

    list.innerHTML = items.map(item => {
        const unitPrice = parseFloat(item.unit_price || item.price) || 0;
        const lineTotal = parseFloat(item.line_total || (unitPrice * item.quantity)) || 0;
        const imgUrl = item.image || '/static/img/defaults/product-placeholder.svg';
        const maxStock = item.available_stock || 999;

        return `
            <div class="cart-item" data-item-id="${item.id}">
                <div class="cart-item-image">
                    <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(item.name)}" />
                </div>
                <div class="cart-item-details">
                    <div class="cart-item-name">${escapeHtml(item.name)}</div>
                    <div class="cart-item-price">₦${formatCurrency(unitPrice)}</div>
                    <div class="cart-item-stock">
                        ${item.available_stock !== undefined ? `${item.available_stock} in stock` : 'In stock'}
                    </div>
                </div>

                <div class="cart-item-qty-box">
                    <button type="button" class="cart-qty-btn btn-dec" data-item-id="${item.id}">−</button>
                    <input
                        type="number"
                        class="cart-qty-input"
                        min="1"
                        max="${maxStock}"
                        value="${item.quantity}"
                        data-cart-quantity="${item.id}"
                        aria-label="Quantity for ${escapeHtml(item.name)}"
                    />
                    <button type="button" class="cart-qty-btn btn-inc" data-item-id="${item.id}">+</button>
                </div>

                <div class="cart-item-total">
                    ₦${formatCurrency(lineTotal)}
                </div>

                <button
                    type="button"
                    class="cart-remove-btn"
                    data-remove-cart-item="${item.id}"
                    aria-label="Remove ${escapeHtml(item.name)} from cart"
                    title="Remove item"
                >
                    <i class="bi bi-trash3"></i>
                </button>
            </div>
        `;
    }).join('');

    // Attach quantity and remove handlers
    list.querySelectorAll('[data-remove-cart-item]').forEach(button => {
        button.addEventListener('click', async () => {
            const productId = button.dataset.removeCartItem;
            button.disabled = true;
            const response = await apiRequest('/customer/cart/items/', {
                method: 'POST',
                body: {
                    product_id: productId,
                    action: 'remove',
                },
            });
            if (response.success) {
                currentCartData = response.data;
                renderCart();
            } else {
                alert(response.message || 'Unable to remove item.');
                loadAndRenderCart();
            }
        });
    });

    list.querySelectorAll('.btn-dec').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = btn.dataset.itemId;
            const input = list.querySelector(`input[data-cart-quantity="${pid}"]`);
            if (input) {
                const current = parseInt(input.value) || 1;
                if (current > 1) {
                    input.value = current - 1;
                    input.dispatchEvent(new Event('change'));
                }
            }
        });
    });

    list.querySelectorAll('.btn-inc').forEach(btn => {
        btn.addEventListener('click', () => {
            const pid = btn.dataset.itemId;
            const input = list.querySelector(`input[data-cart-quantity="${pid}"]`);
            if (input) {
                const current = parseInt(input.value) || 1;
                input.value = current + 1;
                input.dispatchEvent(new Event('change'));
            }
        });
    });

    list.querySelectorAll('[data-cart-quantity]').forEach(input => {
        input.addEventListener('change', async () => {
            const productId = input.dataset.cartQuantity;
            const quantity = Number.parseInt(input.value, 10);
            if (isNaN(quantity) || quantity <= 0) {
                input.value = '1';
                return;
            }

            const response = await apiRequest('/customer/cart/items/', {
                method: 'POST',
                body: {
                    product_id: productId,
                    quantity: quantity,
                    action: 'update',
                },
            });

            if (response.success) {
                currentCartData = response.data;
                renderCart();
            } else {
                alert(response.message || 'Unable to update quantity.');
                loadAndRenderCart();
            }
        });
    });

    updateSummary();
    updateHeaderBadge(currentCartData.item_count || 0);
}

function updateSummary() {
    const subtotal = currentCartData.subtotal || '0.00';
    const total = currentCartData.total || subtotal;
    const itemCount = currentCartData.item_count || 0;

    const subtotalElem = document.getElementById('cartSubtotal');
    if (subtotalElem) subtotalElem.textContent = `₦ ${formatCurrency(subtotal)}`;

    const totalElem = document.getElementById('cartTotal');
    if (totalElem) totalElem.textContent = `₦ ${formatCurrency(total)}`;

    const countElem = document.getElementById('cartItemsCount');
    if (countElem) countElem.textContent = `You have ${itemCount} item${itemCount === 1 ? '' : 's'} in your shopping bag.`;
}

function updateHeaderBadge(count) {
    if (typeof window.updateCustomerCartBadge === 'function') {
        window.updateCustomerCartBadge(count);
    }
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
