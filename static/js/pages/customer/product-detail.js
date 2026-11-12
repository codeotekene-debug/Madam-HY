/**
 * MADAM HY - Modern Customer Product Detail View & Interaction Controller
 */

let currentProduct = null;
window.madamHyCart = window.madamHyCart || [];

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initZoomAndThumbnails();
    initVariantPills();
    loadProductDetail();
    bindActions();
    bindRelatedProducts();
});

function initTabs() {
    const tabTriggers = Array.from(document.querySelectorAll('.tab-trigger'));
    const tabPanels = document.querySelectorAll('.tab-panel');
    if (!tabTriggers.length) return;

    const activate = trigger => {
        tabTriggers.forEach(tab => {
            const selected = tab === trigger;
            tab.classList.toggle('active', selected);
            tab.setAttribute('aria-selected', String(selected));
            tab.tabIndex = selected ? 0 : -1;
        });
        tabPanels.forEach(panel => {
            const selected = panel.id === trigger.getAttribute('aria-controls');
            panel.classList.toggle('active', selected);
            panel.hidden = !selected;
        });
    };

    tabTriggers.forEach((trigger, index) => {
        trigger.addEventListener('click', () => activate(trigger));
        trigger.addEventListener('keydown', event => {
            let nextIndex = index;
            if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabTriggers.length;
            else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabTriggers.length) % tabTriggers.length;
            else if (event.key === 'Home') nextIndex = 0;
            else if (event.key === 'End') nextIndex = tabTriggers.length - 1;
            else return;
            event.preventDefault();
            tabTriggers[nextIndex].focus();
            activate(tabTriggers[nextIndex]);
        });
    });
}

function initZoomAndThumbnails() {
    const mainImgWrapper = document.getElementById('mainImageWrapper');
    const mainImg = document.getElementById('productImage');

    if (mainImgWrapper && mainImg) {
        mainImgWrapper.addEventListener('mousemove', (e) => {
            const rect = mainImgWrapper.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * 100;
            const y = ((e.clientY - rect.top) / rect.height) * 100;
            mainImg.style.transformOrigin = `${x}% ${y}%`;
        });

        mainImgWrapper.addEventListener('mouseleave', () => {
            mainImg.style.transformOrigin = 'center center';
        });
    }

    bindThumbnails();
}

function bindThumbnails() {
    const thumbBtns = document.querySelectorAll('.thumb-btn');
    const mainImg = document.getElementById('productImage');

    thumbBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            thumbBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const src = btn.dataset.src;
            if (src && mainImg) {
                mainImg.src = src;
            }
        });
    });
}

function initVariantPills() {
    const pills = document.querySelectorAll('.variant-pill');
    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
        });
    });
}

async function loadProductDetail() {
    const productId = getProductIdFromUrl();
    if (!productId) return;

    const response = await apiRequest(`/customer/products/${productId}/?format=json`);
    if (!response.success || !response.data) return;

    currentProduct = response.data.product || response.data;
    renderDetail();
}

function renderDetail() {
    if (!currentProduct) return;

    const image = currentProduct.primary_image?.url || currentProduct.images?.[0]?.url;
    if (image) {
        document.getElementById('productImage')?.setAttribute('src', image);
    }
    document.getElementById('productImage')?.setAttribute('alt', currentProduct.name);
    document.getElementById('productName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('breadcrumbName')?.replaceChildren(document.createTextNode(currentProduct.name));

    const categoryName = currentProduct.category?.name || 'Store';
    document.getElementById('productCategory')?.replaceChildren(document.createTextNode(categoryName));
    document.getElementById('breadcrumbCategory')?.replaceChildren(document.createTextNode(categoryName));

    // Pricing
    const numericPrice = parseFloat(currentProduct.selling_price) || 0;
    document.getElementById('productPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(numericPrice)}`));

    const origEl = document.getElementById('productOriginalPrice');
    if (origEl) {
        if (currentProduct.original_price && parseFloat(currentProduct.original_price) > numericPrice) {
            origEl.textContent = `₦ ${formatCurrency(parseFloat(currentProduct.original_price))}`;
            origEl.style.display = '';
        } else {
            origEl.style.display = 'none';
        }
    }

    // Description
    if (currentProduct.description) {
        document.getElementById('productDescription')?.replaceChildren(document.createTextNode(currentProduct.description));
        const tabDesc = document.getElementById('tabDescText');
        if (tabDesc) tabDesc.replaceChildren(document.createTextNode(currentProduct.description));
    }

    // Stock Status
    const quantity = currentProduct.stock?.quantity ?? 0;
    const stockStatus = document.getElementById('productStockStatus');
    if (stockStatus) {
        if (quantity <= 0 || currentProduct.stock?.is_out_of_stock) {
            stockStatus.className = 'detail-stock status-out-of-stock';
            stockStatus.textContent = 'Out of Stock';
        } else if (quantity <= 5) {
            stockStatus.className = 'detail-stock status-low-stock';
            stockStatus.textContent = `Only ${quantity} Left`;
        } else {
            stockStatus.className = 'detail-stock status-in-stock';
            stockStatus.textContent = 'In Stock';
        }
    }

    // Specifications Tab
    document.getElementById('detailName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('detailCategory')?.replaceChildren(document.createTextNode(categoryName));
    document.getElementById('detailPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(numericPrice)}`));
    document.getElementById('detailStock')?.replaceChildren(document.createTextNode(`${quantity} units available`));

    // SKU
    const skuElem = document.getElementById('productSku');
    if (skuElem && currentProduct.sku) {
        skuElem.textContent = currentProduct.sku;
    }

    // Render Dynamic Thumbnails if available
    renderDynamicThumbnails(currentProduct.images || []);

    // Manage purchase CTAs based on authoritative physical stock
    const isOutOfStock = quantity <= 0 || currentProduct.stock?.is_out_of_stock;
    const addBtn = document.getElementById('addToCartBtn');
    const buyBtn = document.getElementById('buyNowBtn');
    const qtyInput = document.getElementById('quantityInput');
    const qtyDec = document.getElementById('quantityDecrement');
    const qtyInc = document.getElementById('quantityIncrement');

    if (isOutOfStock) {
        addBtn?.setAttribute('disabled', 'true');
        addBtn?.setAttribute('style', 'opacity: 0.6; cursor: not-allowed;');
        buyBtn?.setAttribute('disabled', 'true');
        buyBtn?.setAttribute('style', 'opacity: 0.6; cursor: not-allowed;');
        qtyInput?.setAttribute('disabled', 'true');
        qtyDec?.setAttribute('disabled', 'true');
        qtyInc?.setAttribute('disabled', 'true');
        const span = addBtn?.querySelector('span');
        if (span) span.textContent = 'Out of Stock';
    } else {
        addBtn?.removeAttribute('disabled');
        addBtn?.removeAttribute('style');
        buyBtn?.removeAttribute('disabled');
        buyBtn?.removeAttribute('style');
        qtyInput?.removeAttribute('disabled');
        qtyDec?.removeAttribute('disabled');
        qtyInc?.removeAttribute('disabled');
        const span = addBtn?.querySelector('span');
        if (span) span.textContent = 'Add to Cart';
    }
}

function renderDynamicThumbnails(images) {
    const strip = document.getElementById('productThumbnails');
    if (!strip || !images || images.length <= 1) return;

    strip.innerHTML = images.map((img, idx) => `
        <button type="button" class="thumb-btn ${idx === 0 ? 'active' : ''}" data-src="${img.url}" aria-label="View thumbnail ${idx + 1}">
            <img src="${img.url}" alt="${img.alt_text || 'Thumbnail'}" />
        </button>
    `).join('');

    bindThumbnails();
}

function bindActions() {
    const quantityInput = document.getElementById('quantityInput');
    const addBtn = document.getElementById('addToCartBtn');
    const buyNowBtn = document.getElementById('buyNowBtn');
    const continueBtn = document.getElementById('continueShoppingBtn');
    const decrement = document.getElementById('quantityDecrement');
    const increment = document.getElementById('quantityIncrement');

    quantityInput?.addEventListener('change', (e) => {
        const value = parseInt(e.target.value) || 1;
        const maxAttr = parseInt(e.target.getAttribute('max')) || 999;
        const maxStock = currentProduct?.stock?.quantity ?? maxAttr;
        e.target.value = Math.max(1, Math.min(value, maxStock));
    });

    decrement?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        if (quantityInput) quantityInput.value = String(Math.max(1, current - 1));
    });

    increment?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        const maxAttr = parseInt(quantityInput?.getAttribute('max')) || 999;
        const maxStock = currentProduct?.stock?.quantity ?? maxAttr;
        if (quantityInput) quantityInput.value = String(Math.min(current + 1, maxStock));
    });

    addBtn?.addEventListener('click', async () => {
        await executeAddToCart(false);
    });

    buyNowBtn?.addEventListener('click', async () => {
        await executeAddToCart(true);
    });

    continueBtn?.addEventListener('click', () => {
        window.location.href = '/customer/products/';
    });
}

async function executeAddToCart(redirectCheckout = false) {
    const productId = currentProduct?.id || getProductIdFromUrl();
    if (!productId) return;

    const quantityInput = document.getElementById('quantityInput');
    const quantity = parseInt(quantityInput?.value || '1');
    const addBtn = document.getElementById('addToCartBtn');
    const buyBtn = document.getElementById('buyNowBtn');

    if (addBtn) addBtn.disabled = true;
    if (buyBtn) buyBtn.disabled = true;

    const response = await apiRequest('/customer/cart/items/', {
        method: 'POST',
        body: {
            product_id: productId,
            quantity: quantity,
            action: 'add',
        },
    });

    if (addBtn) addBtn.disabled = false;
    if (buyBtn) buyBtn.disabled = false;

    if (response.success) {
        if (typeof window.updateCustomerCartBadge === 'function') {
            window.updateCustomerCartBadge(response.data?.item_count);
        }

        if (redirectCheckout) {
            window.location.href = '/customer/checkout/';
            return;
        }

        const successAlert = document.getElementById('productSuccessAlert');
        const prodName = currentProduct?.name || 'Product';
        if (successAlert) {
            successAlert.textContent = `✓ ${quantity} × ${prodName} added to cart!`;
            successAlert.classList.remove('hidden');
            setTimeout(() => {
                successAlert.classList.add('hidden');
            }, 3500);
        }
    } else {
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            return;
        }
        const errorMsg = response.message || (response.errors ? Object.values(response.errors).flat().join('\n') : 'Unable to add product to cart.');
        alert(errorMsg);
    }
}

function bindRelatedProducts() {
    const quickAddBtns = document.querySelectorAll('.btn-quick-add');
    quickAddBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const productId = btn.dataset.productId;
            const productName = btn.dataset.productName || 'Product';
            if (!productId) return;

            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i>';

            const response = await apiRequest('/customer/cart/items/', {
                method: 'POST',
                body: {
                    product_id: productId,
                    quantity: 1,
                    action: 'add',
                },
            });

            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check2"></i> Added';

            if (response.success) {
                if (typeof window.updateCustomerCartBadge === 'function') {
                    window.updateCustomerCartBadge(response.data?.item_count);
                }
                setTimeout(() => {
                    btn.innerHTML = '<i class="bi bi-plus-lg"></i> Add';
                }, 2000);
            } else {
                if (response.status === 401) {
                    window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
                    return;
                }
                alert(response.message || 'Unable to add item.');
                btn.innerHTML = '<i class="bi bi-plus-lg"></i> Add';
            }
        });
    });
}

function getProductIdFromUrl() {
    const pathMatch = window.location.pathname.match(/\/products\/([^\/]+)\/?$/);
    if (pathMatch && pathMatch[1]) {
        return pathMatch[1];
    }
    return new URLSearchParams(window.location.search).get('id') || null;
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
