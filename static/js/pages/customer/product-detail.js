/**
 * MADAM HY - Customer Product Detail
 * Product detail view for customers
 */

let currentProduct = null;
window.madamHyCart = window.madamHyCart || [];

document.addEventListener('DOMContentLoaded', () => {
    loadProductDetail();
    bindActions();
});

async function loadProductDetail() {
    const productId = getProductIdFromUrl();
    if (!productId) {
        showDetailMessage('Product ID was not found.');
        return;
    }
    const response = await apiRequest(`/products/${productId}/`);
    if (!response.success || !response.data) {
        showDetailMessage(response.message || 'Unable to load product details.');
        return;
    }
    currentProduct = response.data;
    renderDetail();
}

function renderDetail() {
    if (!currentProduct) return;

    const image = currentProduct.primary_image?.url || currentProduct.images?.[0]?.url || 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
    document.getElementById('productImage')?.setAttribute('src', image);
    document.getElementById('productImage')?.setAttribute('alt', currentProduct.name);
    document.getElementById('productName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('productCategory')?.replaceChildren(document.createTextNode(currentProduct.category?.name || 'Uncategorised'));
    document.getElementById('productPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(currentProduct.selling_price)}`));
    document.getElementById('productDescription')?.replaceChildren(document.createTextNode(currentProduct.description));
    document.getElementById('productStockStatus')?.replaceChildren(document.createTextNode(getStockStatus(currentProduct.stock?.status)));
    const stockStatus = document.getElementById('productStockStatus');
    if (stockStatus) stockStatus.className = `detail-stock status-${normalizeStatus(currentProduct.stock?.status)}`;

    document.getElementById('detailName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('detailCategory')?.replaceChildren(document.createTextNode(currentProduct.category?.name || 'Uncategorised'));
    document.getElementById('detailPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(currentProduct.selling_price)}`));
    document.getElementById('detailStock')?.replaceChildren(document.createTextNode(`${currentProduct.stock?.quantity ?? 0} available`));

    if (currentProduct.stock?.is_out_of_stock) {
        document.getElementById('addToCartBtn')?.setAttribute('disabled', 'true');
        document.getElementById('quantityInput')?.setAttribute('disabled', 'true');
        document.getElementById('quantityDecrement')?.setAttribute('disabled', 'true');
        document.getElementById('quantityIncrement')?.setAttribute('disabled', 'true');
    }
}

function bindActions() {
    const quantityInput = document.getElementById('quantityInput');
    const addBtn = document.getElementById('addToCartBtn');
    const continueBtn = document.getElementById('continueShoppingBtn');
    const decrement = document.getElementById('quantityDecrement');
    const increment = document.getElementById('quantityIncrement');

    quantityInput?.addEventListener('change', (e) => {
        const value = parseInt(e.target.value) || 1;
        e.target.value = Math.max(1, Math.min(value, currentProduct?.stock?.quantity ?? 1));
    });

    decrement?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        if (quantityInput) quantityInput.value = String(Math.max(1, current - 1));
    });

    increment?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        if (quantityInput) quantityInput.value = String(Math.min(current + 1, currentProduct.stock?.quantity ?? 0));
    });

    addBtn?.addEventListener('click', () => {
        const quantity = parseInt(quantityInput?.value || '1');
        const cart = window.madamHyCart;
        const existing = cart.find(item => item.id === currentProduct.id);
        if (existing) {
            existing.quantity += quantity;
        } else {
            cart.push({
                id: currentProduct.id,
                name: currentProduct.name,
                price: Number(currentProduct.selling_price),
                quantity,
                image: currentProduct.primary_image?.url || currentProduct.images?.[0]?.url || '',
            });
        }
        const successAlert = document.getElementById('productSuccessAlert');
        if (successAlert) {
            successAlert.textContent = `${quantity} × ${currentProduct.name} added to cart!`;
            successAlert.classList.remove('hidden');
            setTimeout(() => {
                successAlert.classList.add('hidden');
            }, 3000);
        }
        if (quantityInput) quantityInput.value = '1';
    });

    continueBtn?.addEventListener('click', () => {
        window.location.href = '/preview/customer/products/';
    });
}

function getProductIdFromUrl() {
    return Number(new URLSearchParams(window.location.search).get('id')) || null;
}

function getStockStatus(status) {
    switch (normalizeStatus(status)) {
        case 'in-stock':
            return 'In stock';
        case 'low-stock':
            return 'Low stock';
        case 'out-of-stock':
            return 'Out of stock';
        default:
            return 'Out of stock';
    }
}

function normalizeStatus(status) {
    return String(status || 'OUT_OF_STOCK').toLowerCase().replaceAll('_', '-');
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
