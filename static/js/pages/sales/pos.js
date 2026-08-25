const posProducts = [];
const cart = [];

document.addEventListener('DOMContentLoaded', () => {
    bindPosEvents();
    loadProducts();
    updateCartSummary();
});

function bindPosEvents() {
    document.getElementById('productSearchInput')?.addEventListener('input', renderProducts);
    document.getElementById('categoryFilter')?.addEventListener('change', renderProducts);
    document.getElementById('discountInput')?.addEventListener('input', updateCartSummary);
    document.getElementById('amountReceivedInput')?.addEventListener('input', updateCartSummary);
    document.getElementById('paymentMethodSelect')?.addEventListener('change', updatePaymentFields);
    document.getElementById('clearCartBtn')?.addEventListener('click', clearCart);
    document.getElementById('checkoutBtn')?.addEventListener('click', createDraftSale);
    document.getElementById('productRetryBtn')?.addEventListener('click', loadProducts);
    document.getElementById('toggleCatalogBtn')?.addEventListener('click', () => {
        const list = document.getElementById('productList');
        const button = document.getElementById('toggleCatalogBtn');
        if (!list || !button) return;
        list.classList.toggle('compact-grid');
        button.textContent = list.classList.contains('compact-grid') ? 'List view' : 'Grid view';
    });
    document.getElementById('openQuickAddBtn')?.addEventListener('click', () => {
        const firstAvailable = posProducts.find(product => product.stock.quantity > 0);
        if (!firstAvailable) {
            showMessage('No available products in stock.', 'error');
            return;
        }
        addToCart(firstAvailable.id, 1);
    });
    updatePaymentFields();
}

async function loadProducts() {
    const productList = document.getElementById('productList');
    if (!productList) return;
    productList.innerHTML = loadingRow('Loading products...');
    const response = await apiRequest('/products/?page_size=100&sort_by=name');
    if (!response.success) {
        productList.innerHTML = '';
        showEmptyState('Product catalogue could not load. Try again.', true);
        showMessage(response.message || 'Product catalogue could not load.', 'error');
        return;
    }

    posProducts.length = 0;
    (response.data?.products || []).forEach(product => {
        if (!product.is_active) return;
        posProducts.push({
            id: product.id,
            name: product.name,
            category: product.category?.name || 'Uncategorised',
            sku: product.sku,
            price: Number(product.selling_price || 0),
            stock: product.stock || { quantity: 0, status: 'OUT_OF_STOCK' },
            image: product.image?.url || '',
        });
    });
    populateCategoryFilter();
    renderProducts();
}

function populateCategoryFilter() {
    const select = document.getElementById('categoryFilter');
    if (!select) return;
    const selected = select.value;
    const categories = [...new Set(posProducts.map(product => product.category))].sort();
    select.innerHTML = '<option value="all">All categories</option>' + categories.map(category => (
        `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`
    )).join('');
    select.value = categories.includes(selected) ? selected : 'all';
}

function renderProducts() {
    const productList = document.getElementById('productList');
    const query = document.getElementById('productSearchInput')?.value.trim().toLowerCase() || '';
    const category = document.getElementById('categoryFilter')?.value || 'all';
    if (!productList) return;

    const products = posProducts.filter(product => {
        const matchesQuery = !query || [product.name, product.category, product.sku]
            .some(value => value.toLowerCase().includes(query));
        return matchesQuery && (category === 'all' || product.category === category);
    });
    if (!products.length) {
        productList.innerHTML = '';
        showEmptyState('No products match this search.', false);
        return;
    }

    showEmptyState('', false);
    productList.innerHTML = products.map(product => {
        const quantity = Number(product.stock.quantity || 0);
        const status = product.stock.status || (quantity ? 'IN_STOCK' : 'OUT_OF_STOCK');
        return `
            <article class="product-card-pos" aria-label="${escapeHtml(product.name)}">
                <div class="pos-product-image">${product.image ? `<img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" />` : ''}</div>
                <div class="pos-product-body">
                    <div class="pos-product-top">
                        <span class="pos-product-category">${escapeHtml(product.category)}</span>
                        <span class="pos-product-price">NGN ${formatCurrency(product.price)}</span>
                    </div>
                    <div class="pos-product-name">${escapeHtml(product.name)}</div>
                    <div class="pos-product-meta"><span>${escapeHtml(product.sku)}</span><span>${formatNumber(quantity)} available</span></div>
                    <div class="pos-product-actions">
                        <span class="stock-chip ${stockClass(status)}">${formatStockLabel(status)}</span>
                        <button type="button" class="btn btn-primary btn-sm" data-add-product="${product.id}" ${quantity <= 0 ? 'disabled' : ''}>Add</button>
                    </div>
                </div>
            </article>
        `;
    }).join('');
    productList.querySelectorAll('[data-add-product]').forEach(button => {
        button.addEventListener('click', () => addToCart(Number(button.dataset.addProduct), 1));
    });
}

function addToCart(productId, quantity) {
    const product = posProducts.find(item => item.id === productId);
    if (!product || product.stock.quantity <= 0) {
        showMessage('This product is unavailable or out of stock.', 'error');
        return;
    }
    const existing = cart.find(item => item.product_id === productId);
    const nextQuantity = (existing?.quantity || 0) + quantity;
    if (nextQuantity > product.stock.quantity) {
        showMessage('Cart quantity cannot exceed available stock.', 'error');
        return;
    }
    if (existing) existing.quantity = nextQuantity;
    else cart.push({
        product_id: product.id,
        name: product.name,
        sku: product.sku,
        quantity,
        price: product.price,
        stock: product.stock.quantity,
        discount: '0.00',
    });
    updateCartSummary();
    showMessage(`${product.name} added to cart.`, 'success');
}

function updateCartSummary() {
    const cartItems = document.getElementById('cartItems');
    const emptyState = document.getElementById('cartEmptyState');
    if (!cartItems) return;
    if (!cart.length) {
        cartItems.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        setText('cartItemCount', '0 items');
        setText('subtotalValue', 'NGN 0.00');
        setText('totalValue', 'NGN 0.00');
        setText('changeValue', 'NGN 0.00');
        return;
    }
    emptyState?.classList.add('empty-state-hidden');
    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity - Number(item.discount || 0), 0);
    const discount = Math.max(Number(document.getElementById('discountInput')?.value || 0), 0);
    const total = Math.max(subtotal - discount, 0);
    const amount = Math.max(Number(document.getElementById('amountReceivedInput')?.value || 0), 0);
    const change = Math.max(amount - total, 0);
    setText('cartItemCount', `${cart.reduce((sum, item) => sum + item.quantity, 0)} items`);
    setText('subtotalValue', `NGN ${formatCurrency(subtotal)}`);
    setText('totalValue', `NGN ${formatCurrency(total)}`);
    setText('changeValue', `NGN ${formatCurrency(change)}`);
    cartItems.innerHTML = cart.map(item => `
        <div class="cart-item" data-cart-item="${item.product_id}">
            <div class="cart-item-main"><span class="cart-item-name">${escapeHtml(item.name)}</span><div class="cart-item-meta"><span>${escapeHtml(item.sku)}</span><span>${formatNumber(item.stock)} in stock</span></div></div>
            <div class="cart-item-actions">
                <div class="qty-control" aria-label="Quantity controls for ${escapeHtml(item.name)}"><button type="button" data-decrease="${item.product_id}" aria-label="Decrease quantity">-</button><span>${item.quantity}</span><button type="button" data-increase="${item.product_id}" aria-label="Increase quantity">+</button></div>
                <span class="cart-item-price">NGN ${formatCurrency(item.price * item.quantity)}</span><button type="button" class="cart-item-remove" data-remove="${item.product_id}" aria-label="Remove ${escapeHtml(item.name)}">x</button>
            </div>
        </div>
    `).join('');
    cartItems.querySelectorAll('[data-increase]').forEach(button => button.addEventListener('click', () => increaseQuantity(Number(button.dataset.increase))));
    cartItems.querySelectorAll('[data-decrease]').forEach(button => button.addEventListener('click', () => decreaseQuantity(Number(button.dataset.decrease))));
    cartItems.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => removeFromCart(Number(button.dataset.remove))));
}

function increaseQuantity(productId) { addToCart(productId, 1); }

function decreaseQuantity(productId) {
    const item = cart.find(entry => entry.product_id === productId);
    if (!item) return;
    if (item.quantity <= 1) removeFromCart(productId);
    else { item.quantity -= 1; updateCartSummary(); }
}

function removeFromCart(productId) {
    const index = cart.findIndex(item => item.product_id === productId);
    if (index >= 0) cart.splice(index, 1);
    updateCartSummary();
}

function clearCart() {
    cart.length = 0;
    document.getElementById('discountInput').value = '0';
    document.getElementById('amountReceivedInput').value = '';
    updateCartSummary();
    showMessage('Cart cleared.', 'success');
}

async function createDraftSale() {
    if (!cart.length) {
        showMessage('Add products to the cart before checking out.', 'error');
        return;
    }
    const paymentMethod = document.getElementById('paymentMethodSelect')?.value || 'CASH';
    const customerId = document.getElementById('customerIdInput')?.value.trim() || null;
    if (paymentMethod === 'CREDIT' && !customerId) {
        showMessage('Customer ID is required for credit sales.', 'error');
        return;
    }
    const button = document.getElementById('checkoutBtn');
    setButtonLoading(button, 'Creating draft...');
    const response = await apiRequest('/sales/', {
        method: 'POST',
        body: {
            customer_id: customerId ? Number(customerId) : null,
            payment_method: paymentMethod,
            discount: String(Math.max(Number(document.getElementById('discountInput')?.value || 0), 0).toFixed(2)),
            notes: '',
            items: cart.map(item => ({ product_id: item.product_id, quantity: item.quantity, discount: item.discount })),
        },
    });
    setButtonLoading(button, 'Checkout');
    if (!response.success) {
        showMessage(formatApiError(response), 'error');
        return;
    }
    const sale = response.data?.sale;
    if (!sale?.id) {
        showMessage('The draft sale response was incomplete.', 'error');
        return;
    }
    sessionStorage.setItem('madamHyDraftSale', JSON.stringify({ sale, items: response.data.items || [] }));
    window.location.href = `/preview/sales/checkout/?sale_id=${sale.id}`;
}

function updatePaymentFields() {
    const paymentMethod = document.getElementById('paymentMethodSelect')?.value;
    const customerGroup = document.getElementById('customerIdGroup');
    const amountInput = document.getElementById('amountReceivedInput');
    customerGroup?.classList.toggle('payment-field-hidden', paymentMethod !== 'CREDIT');
    if (amountInput) amountInput.disabled = paymentMethod !== 'CASH';
}

function showEmptyState(message, error) {
    const emptyState = document.getElementById('productEmptyState');
    if (!emptyState) return;
    emptyState.classList.toggle('inventory-load-error', error);
    emptyState.classList.toggle('empty-state-hidden', !message);
    const paragraph = emptyState.querySelector('p');
    if (paragraph && message) paragraph.textContent = message;
}

function loadingRow(message) { return `<div class="empty-state">${escapeHtml(message)}</div>`; }
function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = value; }
function setButtonLoading(button, label) { if (button) { button.disabled = label !== 'Checkout'; button.textContent = label; } }
function stockClass(status) { return String(status).toLowerCase().replaceAll('_', '-'); }
function formatStockLabel(status) { return String(status || 'OUT_OF_STOCK').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, char => char.toUpperCase()); }
function formatNumber(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function formatApiError(response) { return response.errors ? Object.values(response.errors).flat().join(' ') : (response.message || 'Request failed.'); }
function showMessage(message, type = '') { const element = document.getElementById('saleMessage'); if (!element) return; element.textContent = message; element.className = `sale-message ${type}`; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }