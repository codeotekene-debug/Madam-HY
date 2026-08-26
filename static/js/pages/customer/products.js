/**
 * MADAM HY - Customer Products Browsing
 * Frontend-only product catalog for customers
 */

window.madamHyCart = window.madamHyCart || [];
const customerCart = window.madamHyCart;
const customerProductState = { page: 1, pageSize: 10, requestId: 0 };
const customerProductPlaceholder = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

document.addEventListener('DOMContentLoaded', () => {
    setupFilters();
    loadCategories();
    loadProducts();
    setupPagination();
    updateCartCount();
});

function setupFilters() {
    const search = document.getElementById('customerProductSearch');
    const category = document.getElementById('customerCategoryFilter');
    const stock = document.getElementById('customerStockFilter');
    const sort = document.getElementById('customerSortSelect');

    const applyFilters = () => {
        customerProductState.page = 1;
        loadProducts();
    };
    let searchTimer;
    search?.addEventListener('input', () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(applyFilters, 300);
    });
    category?.addEventListener('change', applyFilters);
    stock?.addEventListener('change', applyFilters);
    sort?.addEventListener('change', applyFilters);
}

function setupPagination() {
    document.getElementById('customerProductsPrevious')?.addEventListener('click', () => {
        if (customerProductState.page > 1) {
            customerProductState.page -= 1;
            loadProducts();
        }
    });
    document.getElementById('customerProductsNext')?.addEventListener('click', () => {
        customerProductState.page += 1;
        loadProducts();
    });
}

async function loadProducts() {
    const grid = document.getElementById('customerProductGrid');
    const empty = document.getElementById('customerProductsEmpty');
    if (!grid) return;

    const params = new URLSearchParams({
        page: String(customerProductState.page),
        page_size: String(customerProductState.pageSize),
        search: document.getElementById('customerProductSearch')?.value.trim() || '',
        category: getFilterValue('customerCategoryFilter'),
        stock: getFilterValue('customerStockFilter'),
        sort_by: document.getElementById('customerSortSelect')?.value || 'name'
    });
    ['search', 'category', 'stock'].forEach(key => {
        if (!params.get(key)) params.delete(key);
    });

    const requestId = ++customerProductState.requestId;
    const response = await apiRequest(`/products/?${params.toString()}`);
    if (requestId !== customerProductState.requestId) return;
    if (!response.success) {
        grid.replaceChildren();
        empty?.classList.add('empty-state-hidden');
        showCustomerProductMessage(response.message || 'Unable to load products.', true, loadProducts);
        return;
    }

    const products = response.data?.products || [];
    updatePagination(response.data?.pagination || {});

    if (!products.length) {
        grid.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        updateSummary(0);
        return;
    }

    empty?.classList.add('empty-state-hidden');
    hideCustomerProductMessage();
    grid.innerHTML = products.map(product => {
        const status = normalizeStatus(product.stock?.status);
        const image = product.image?.url || customerProductPlaceholder;
        return `
        <div class="customer-product-card">
            <div class="product-card-image">
                <img src="${image}" alt="${product.image?.alt_text || product.name}" onerror="this.src='${customerProductPlaceholder}'" />
            </div>
            <div class="product-card-content">
                <span class="product-card-category">${product.category?.name || 'Uncategorised'}</span>
                <h3 class="product-card-name">${product.name}</h3>
                <div class="product-card-price">₦${formatCurrency(product.selling_price)}</div>
                <div class="product-card-stock">${formatStatus(status, product.stock?.quantity)}</div>
                <div class="product-card-actions">
                    <a href="/preview/customer/product-detail/?id=${product.id}" class="btn btn-secondary btn-sm">View</a>
                    <button type="button" class="btn btn-primary btn-sm" data-product-id="${product.id}">Add</button>
                </div>
            </div>
        </div>
    `;
    }).join('');

    grid.querySelectorAll('[data-product-id]').forEach(button => {
        button.addEventListener('click', () => {
            const product = products.find(item => String(item.id) === button.dataset.productId);
            if (product) addProductToCart(product);
        });
    });

    updateSummary(response.data?.pagination?.total_count || products.length);
}

async function loadCategories() {
    const select = document.getElementById('customerCategoryFilter');
    if (!select) return;
    const response = await apiRequest('/products/categories/');
    if (!response.success) return;
    const selected = select.value;
    select.replaceChildren(new Option('All categories', 'all'));
    (response.data?.categories || []).forEach(category => select.add(new Option(category.name, category.slug)));
    select.value = selected;
}

function getFilterValue(id) {
    const value = document.getElementById(id)?.value || '';
    return value === 'all' ? '' : value;
}

function normalizeStatus(status) {
    return String(status || 'OUT_OF_STOCK').toLowerCase().replaceAll('_', '-');
}

function formatStatus(status, quantity = 0) {
    if (status === 'in-stock') return 'In stock';
    if (status === 'low-stock') return `Low stock (${quantity} left)`;
    return 'Out of stock';
}

function updatePagination(pagination) {
    const page = pagination.page || customerProductState.page;
    const totalPages = pagination.total_pages || 0;
    customerProductState.page = page;
    const previous = document.getElementById('customerProductsPrevious');
    const next = document.getElementById('customerProductsNext');
    if (previous) previous.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages || totalPages === 0;
    document.getElementById('customerProductsPage')?.replaceChildren(document.createTextNode(`Page ${page} of ${totalPages}`));
}

function showCustomerProductMessage(message, isError, retry) {
    const empty = document.getElementById('customerProductsEmpty');
    if (!empty) return;
    empty.replaceChildren();
    const text = document.createElement('p');
    text.textContent = message;
    empty.append(text);
    if (isError && retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Retry';
        button.addEventListener('click', retry);
        empty.append(button);
    }
    empty.classList.remove('empty-state-hidden');
}

function hideCustomerProductMessage() {
    document.getElementById('customerProductsEmpty')?.classList.add('empty-state-hidden');
}

function updateSummary(count) {
    document.getElementById('availableProductsCount')?.replaceChildren(document.createTextNode(String(count)));
}

function addProductToCart(product, quantity = 1) {
    const existing = customerCart.find(item => item.id === product.id);
    if (existing) {
        existing.quantity += quantity;
    } else {
        customerCart.push({
            id: product.id,
            name: product.name,
            price: Number(product.selling_price),
            quantity,
            image: product.image?.url || customerProductPlaceholder,
        });
    }
    updateCartCount();
    alert(`${quantity} × ${product.name} added to cart!`);
}

function updateCartCount() {
    const count = customerCart.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('cartItemCount')?.replaceChildren(document.createTextNode(String(count)));
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
