const posProducts = [
    {
        id: 1,
        name: 'Green Ankara Fabric Premium',
        category: 'Fashion',
        sku: 'MH-FAB-104',
        price: 12500,
        stock: 24,
        status: 'in-stock',
        image: 'https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=900&q=80'
    },
    {
        id: 2,
        name: 'Velvet Evening Gown',
        category: 'Fashion',
        sku: 'MH-GOW-22',
        price: 28000,
        stock: 7,
        status: 'low-stock',
        image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80'
    },
    {
        id: 3,
        name: 'Radiant Glow Serum',
        category: 'Beauty',
        sku: 'MH-BEA-58',
        price: 9500,
        stock: 18,
        status: 'in-stock',
        image: 'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=900&q=80'
    },
    {
        id: 4,
        name: 'Kitchen Storage Basket',
        category: 'Home',
        sku: 'MH-HOM-15',
        price: 6200,
        stock: 3,
        status: 'low-stock',
        image: 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80'
    },
    {
        id: 5,
        name: 'Wireless Speaker Mini',
        category: 'Electronics',
        sku: 'MH-ELE-41',
        price: 22000,
        stock: 0,
        status: 'out-of-stock',
        image: 'https://images.unsplash.com/photo-1518444065439-e933c06ce9cd?auto=format&fit=crop&w=900&q=80'
    },
    {
        id: 6,
        name: 'Leather Office Tote',
        category: 'Fashion',
        sku: 'MH-ACC-77',
        price: 18500,
        stock: 15,
        status: 'in-stock',
        image: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=80'
    }
];

const cart = [];

document.addEventListener('DOMContentLoaded', () => {
    renderProducts();
    bindPosEvents();
    updateCartSummary();
});

function bindPosEvents() {
    const searchInput = document.getElementById('productSearchInput');
    const categoryFilter = document.getElementById('categoryFilter');
    const toggleCatalogBtn = document.getElementById('toggleCatalogBtn');
    const openQuickAddBtn = document.getElementById('openQuickAddBtn');
    const discountInput = document.getElementById('discountInput');
    const amountReceivedInput = document.getElementById('amountReceivedInput');
    const clearCartBtn = document.getElementById('clearCartBtn');
    const checkoutBtn = document.getElementById('checkoutBtn');

    searchInput?.addEventListener('input', renderProducts);
    categoryFilter?.addEventListener('change', renderProducts);
    discountInput?.addEventListener('input', updateCartSummary);
    amountReceivedInput?.addEventListener('input', updateCartSummary);
    clearCartBtn?.addEventListener('click', clearCart);
    checkoutBtn?.addEventListener('click', processCheckout);

    toggleCatalogBtn?.addEventListener('click', () => {
        const list = document.getElementById('productList');
        if (!list) return;
        list.classList.toggle('compact-grid');
        toggleCatalogBtn.textContent = list.classList.contains('compact-grid') ? 'List view' : 'Grid view';
    });

    openQuickAddBtn?.addEventListener('click', () => {
        const firstAvailable = posProducts.find(item => item.status !== 'out-of-stock');
        if (!firstAvailable) {
            showMessage('No available products in stock.', 'error');
            return;
        }
        addToCart(firstAvailable.id, 1);
    });
}

function renderProducts() {
    const productList = document.getElementById('productList');
    const emptyState = document.getElementById('productEmptyState');
    const searchInput = document.getElementById('productSearchInput');
    const categoryFilter = document.getElementById('categoryFilter');

    if (!productList) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const categoryValue = categoryFilter?.value || 'all';

    let filtered = posProducts.filter(product => {
        const matchesQuery = !query || [product.name, product.category, product.sku].some(value => value.toLowerCase().includes(query));
        const matchesCategory = categoryValue === 'all' || product.category === categoryValue;
        return matchesQuery && matchesCategory;
    });

    if (!filtered.length) {
        productList.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    productList.innerHTML = filtered.map(product => `
        <article class="product-card-pos" aria-label="${product.name}">
            <div class="pos-product-image">
                <img src="${product.image}" alt="${product.name}" />
            </div>
            <div class="pos-product-body">
                <div class="pos-product-top">
                    <span class="pos-product-category">${product.category}</span>
                    <span class="pos-product-price">₦ ${formatCurrency(product.price)}</span>
                </div>
                <div class="pos-product-name">${product.name}</div>
                <div class="pos-product-meta">
                    <span>${product.sku}</span>
                    <span>${product.stock} left</span>
                </div>
                <div class="pos-product-actions">
                    <span class="stock-chip ${product.status}">${formatStockLabel(product.status)}</span>
                    <button type="button" class="btn btn-primary btn-sm" data-add-product="${product.id}" ${product.status === 'out-of-stock' ? 'disabled' : ''}>Add</button>
                </div>
            </div>
        </article>
    `).join('');

    document.querySelectorAll('[data-add-product]').forEach(button => {
        button.addEventListener('click', () => addToCart(Number(button.dataset.addProduct), 1));
    });
}

function addToCart(productId, quantity) {
    const product = posProducts.find(item => item.id === productId);
    if (!product || product.status === 'out-of-stock') {
        showMessage('This product is unavailable or out of stock.', 'error');
        return;
    }

    const existing = cart.find(item => item.id === productId);

    if (existing) {
        if (existing.quantity >= product.stock) {
            showMessage('Stock limit reached for this product.', 'error');
            return;
        }
        existing.quantity += quantity;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            price: product.price,
            quantity: quantity,
            stock: product.stock
        });
    }

    updateCartSummary();
    showMessage(`${product.name} added to cart.`, 'success');
}

function updateCartSummary() {
    const cartItems = document.getElementById('cartItems');
    const cartEmptyState = document.getElementById('cartEmptyState');
    const cartItemCount = document.getElementById('cartItemCount');
    const subtotalValue = document.getElementById('subtotalValue');
    const totalValue = document.getElementById('totalValue');
    const changeValue = document.getElementById('changeValue');
    const discountInput = document.getElementById('discountInput');
    const amountReceivedInput = document.getElementById('amountReceivedInput');

    if (!cartItems) return;

    if (!cart.length) {
        cartItems.innerHTML = '';
        cartEmptyState?.classList.remove('empty-state-hidden');
        if (cartItemCount) cartItemCount.textContent = '0 items';
        if (subtotalValue) subtotalValue.textContent = '₦ 0';
        if (totalValue) totalValue.textContent = '₦ 0';
        if (changeValue) changeValue.textContent = '₦ 0';
        return;
    }

    cartEmptyState?.classList.add('empty-state-hidden');

    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const discount = Number(discountInput?.value || 0);
    const total = Math.max(subtotal - discount, 0);
    const amountReceived = Number(amountReceivedInput?.value || 0);
    const change = Math.max(amountReceived - total, 0);

    if (cartItemCount) cartItemCount.textContent = `${cart.reduce((sum, item) => sum + item.quantity, 0)} items`;
    if (subtotalValue) subtotalValue.textContent = `₦ ${formatCurrency(subtotal)}`;
    if (totalValue) totalValue.textContent = `₦ ${formatCurrency(total)}`;
    if (changeValue) changeValue.textContent = `₦ ${formatCurrency(change)}`;

    cartItems.innerHTML = cart.map(item => `
        <div class="cart-item" data-cart-item="${item.id}">
            <div class="cart-item-main">
                <span class="cart-item-name">${item.name}</span>
                <div class="cart-item-meta">
                    <span>₦ ${formatCurrency(item.price)}</span>
                    <span>${item.stock} in stock</span>
                </div>
            </div>

            <div class="cart-item-actions">
                <div class="qty-control" aria-label="Quantity controls for ${item.name}">
                    <button type="button" data-decrease="${item.id}" aria-label="Decrease quantity">−</button>
                    <span>${item.quantity}</span>
                    <button type="button" data-increase="${item.id}" aria-label="Increase quantity">+</button>
                </div>
                <span class="cart-item-price">₦ ${formatCurrency(item.price * item.quantity)}</span>
                <button type="button" class="cart-item-remove" data-remove="${item.id}" aria-label="Remove ${item.name}">×</button>
            </div>
        </div>
    `).join('');

    document.querySelectorAll('[data-increase]').forEach(button => {
        button.addEventListener('click', () => increaseQuantity(Number(button.dataset.increase)));
    });

    document.querySelectorAll('[data-decrease]').forEach(button => {
        button.addEventListener('click', () => decreaseQuantity(Number(button.dataset.decrease)));
    });

    document.querySelectorAll('[data-remove]').forEach(button => {
        button.addEventListener('click', () => removeFromCart(Number(button.dataset.remove)));
    });
}

function increaseQuantity(productId) {
    const product = posProducts.find(item => item.id === productId);
    const current = cart.find(item => item.id === productId);
    if (!product || !current) return;

    if (current.quantity >= product.stock) {
        showMessage('Stock limit reached for this product.', 'error');
        return;
    }

    current.quantity += 1;
    updateCartSummary();
}

function decreaseQuantity(productId) {
    const current = cart.find(item => item.id === productId);
    if (!current) return;

    if (current.quantity <= 1) {
        removeFromCart(productId);
        return;
    }

    current.quantity -= 1;
    updateCartSummary();
}

function removeFromCart(productId) {
    const idx = cart.findIndex(item => item.id === productId);
    if (idx !== -1) {
        cart.splice(idx, 1);
        updateCartSummary();
    }
}

function clearCart() {
    cart.length = 0;
    const discountInput = document.getElementById('discountInput');
    const amountReceivedInput = document.getElementById('amountReceivedInput');
    if (discountInput) discountInput.value = '0';
    if (amountReceivedInput) amountReceivedInput.value = '';
    updateCartSummary();
    showMessage('Cart cleared.', 'success');
}

function processCheckout() {
    const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const discount = Number(document.getElementById('discountInput')?.value || 0);
    const total = Math.max(subtotal - discount, 0);
    const amountReceived = Number(document.getElementById('amountReceivedInput')?.value || 0);

    if (!cart.length) {
        showMessage('Add products to the cart before checking out.', 'error');
        return;
    }

    if (amountReceived < total) {
        showMessage('Amount received is lower than the total due.', 'error');
        return;
    }

    const change = Math.max(amountReceived - total, 0);
    const receipt = {
        number: `MH-${String(Date.now()).slice(-6)}`,
        date: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
        cashier: 'Amina Yusuf',
        payment: document.getElementById('paymentMethodSelect')?.value || 'Cash',
        items: cart.map(item => ({
            name: item.name,
            qty: item.quantity,
            price: item.price,
            total: item.price * item.quantity
        })),
        subtotal,
        discount,
        total,
        change
    };

    localStorage.setItem('madamHyReceipt', JSON.stringify(receipt));
    showMessage('Checkout complete. Receipt is ready.', 'success');
    cart.length = 0;
    document.getElementById('discountInput').value = '0';
    document.getElementById('amountReceivedInput').value = '';
    updateCartSummary();
    window.location.href = '/sales/receipt/';
}

function showMessage(message, type) {
    const saleMessage = document.getElementById('saleMessage');
    if (!saleMessage) return;
    saleMessage.textContent = message;
    saleMessage.className = `sale-message ${type}`;
    window.clearTimeout(showMessage.timeoutId);
    showMessage.timeoutId = window.setTimeout(() => {
        saleMessage.textContent = '';
        saleMessage.className = 'sale-message';
    }, 2400);
}

function formatStockLabel(status) {
    if (status === 'in-stock') return 'In stock';
    if (status === 'low-stock') return 'Low stock';
    return 'Out of stock';
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
