/**
 * MADAM HY - Customer Products Browsing & Catalog Controller
 */

window.madamHyCart = window.madamHyCart || [];
const customerProductState = { page: 1, pageSize: 12, requestId: 0, activeCategory: 'all' };
const customerProductPlaceholder = "/static/img/defaults/product-placeholder.svg";

document.addEventListener('DOMContentLoaded', () => {
    setupFilters();
    setupStoreAdScroller();
    loadCategories();
    loadProducts();
    setupPagination();
    updateCartCount();
});

function setupStoreAdScroller() {
    const button = document.getElementById('storeAdPause');
    const track = document.getElementById('storeAdTrack');
    if (!button || !track) return;

    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
        button.disabled = true;
        button.textContent = 'Motion off';
        button.setAttribute('aria-label', 'Automatic HY STORE promotion movement is disabled by your motion preference');
        return;
    }

    button.addEventListener('click', () => {
        const paused = button.getAttribute('aria-pressed') === 'true';
        const nextPaused = !paused;
        button.setAttribute('aria-pressed', String(nextPaused));
        track.classList.toggle('is-paused', nextPaused);
        button.textContent = nextPaused ? 'Resume' : 'Pause';
        button.setAttribute('aria-label', `${nextPaused ? 'Resume' : 'Pause'} HY STORE promotions`);
    });
}

function setupFilters() {
    const search = document.getElementById('customerProductSearch');
    const clearBtn = document.getElementById('clearSearchBtn');
    const categorySelect = document.getElementById('customerCategoryFilter');
    const stock = document.getElementById('customerStockFilter');
    const sort = document.getElementById('customerSortSelect');
    const resetBtn = document.getElementById('resetFiltersBtn');

    // Read initial URL query parameters (e.g. from global header search or category link)
    const urlParams = new URLSearchParams(window.location.search);
    const initialQuery = urlParams.get('q') || urlParams.get('search') || '';
    const initialCategory = urlParams.get('category') || '';
    const initialPage = Number.parseInt(urlParams.get('page') || '1', 10);
    const initialStock = urlParams.get('stock') || 'all';
    const initialSort = urlParams.get('sort_by') || 'name';

    if (initialQuery && search) {
        search.value = initialQuery;
    }
    if (initialCategory) {
        customerProductState.activeCategory = initialCategory;
    }
    customerProductState.page = Number.isFinite(initialPage) && initialPage > 0 ? initialPage : 1;
    if (stock && ['all', 'IN_STOCK', 'LOW_STOCK', 'OUT_OF_STOCK'].includes(initialStock)) stock.value = initialStock;
    if (sort && ['name', 'price_asc', 'price_desc'].includes(initialSort)) sort.value = initialSort;
    if (window.location.hash === '#customerCategoryFilter') {
        requestAnimationFrame(() => categorySelect?.focus({ preventScroll: true }));
    }

    const updateClearBtn = () => {
        if (clearBtn) {
            clearBtn.hidden = !(search && search.value.trim());
        }
    };
    updateClearBtn();

    const applyFilters = () => {
        customerProductState.page = 1;
        loadProducts();
    };

    let searchTimer;
    search?.addEventListener('input', () => {
        updateClearBtn();
        clearTimeout(searchTimer);
        searchTimer = setTimeout(applyFilters, 300);
    });

    clearBtn?.addEventListener('click', () => {
        if (search) {
            search.value = '';
            updateClearBtn();
            search.focus();
            applyFilters();
        }
    });

    categorySelect?.addEventListener('change', () => {
        syncCategoryPill(categorySelect.value);
        applyFilters();
    });

    stock?.addEventListener('change', applyFilters);
    sort?.addEventListener('change', applyFilters);

    resetBtn?.addEventListener('click', () => {
        if (search) search.value = '';
        updateClearBtn();
        if (categorySelect) categorySelect.value = 'all';
        syncCategoryPill('all');
        if (stock) stock.value = 'all';
        if (sort) sort.value = 'name';
        applyFilters();
    });
}

function syncCategoryPill(val) {
    customerProductState.activeCategory = val || 'all';
    document.querySelectorAll('.category-pill').forEach(pill => {
        const cat = pill.dataset.category || 'all';
        pill.classList.toggle('active', cat === customerProductState.activeCategory);
        pill.setAttribute('aria-pressed', String(cat === customerProductState.activeCategory));
    });
}

function setupPagination() {
    document.getElementById('customerProductsPrevious')?.addEventListener('click', () => {
        if (customerProductState.page > 1) {
            customerProductState.page -= 1;
            loadProducts();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });
    document.getElementById('customerProductsNext')?.addEventListener('click', () => {
        customerProductState.page += 1;
        loadProducts();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

async function loadProducts() {
    const grid = document.getElementById('customerProductGrid');
    const empty = document.getElementById('customerProductsEmpty');
    if (!grid) return;

    const searchTerm = document.getElementById('customerProductSearch')?.value.trim() || '';
    const categoryVal = getFilterValue('customerCategoryFilter') || (customerProductState.activeCategory !== 'all' ? customerProductState.activeCategory : '');
    const stockVal = getFilterValue('customerStockFilter');
    const sortVal = document.getElementById('customerSortSelect')?.value || 'name';

    syncCatalogUrl(searchTerm, categoryVal, stockVal, sortVal);
    grid.setAttribute('aria-busy', 'true');

    const params = new URLSearchParams({
        page: String(customerProductState.page),
        page_size: String(customerProductState.pageSize),
        q: searchTerm,
        search: searchTerm,
        category: categoryVal,
        stock: stockVal,
        sort_by: sortVal,
    });
    ['q', 'search', 'category', 'stock'].forEach(key => {
        if (!params.get(key)) params.delete(key);
    });

    const requestId = ++customerProductState.requestId;
    const response = await apiRequest(`/customer/products/?format=json&${params.toString()}`);
    if (requestId !== customerProductState.requestId) return;
    grid.setAttribute('aria-busy', 'false');

    if (!response.success) {
        grid.replaceChildren();
        empty?.classList.add('empty-state-hidden');
        showCustomerProductMessage(response.message || 'Unable to load products.', true, loadProducts);
        announceProductResults('Product results could not be loaded. Use the retry button to try again.');
        return;
    }

    const products = response.data?.products || [];
    updatePagination(response.data?.pagination || {});

    if (!products.length) {
        grid.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        updateSummary(0);
        announceProductResults('No products match the selected search and filters.');
        return;
    }

    empty?.classList.add('empty-state-hidden');
    hideCustomerProductMessage();

    // Render cards from live catalog data. Do not infer a sale price or promotion.
    const renderedCards = [];
    products.forEach((product) => {
        const numericPrice = parseFloat(product.selling_price) || 0;
        const status = normalizeStatus(product.stock?.status);
        const image = product.image?.url || customerProductPlaceholder;
        const isOutOfStock = status === 'out-of-stock';

        renderedCards.push(`
            <article class="customer-product-card" data-card-id="${product.id}">
                <div class="product-card-image">
                    <a href="/customer/products/${product.id}/" style="display: contents;">
                        <img src="${image}" alt="${product.image?.alt_text || product.name}" onerror="this.src='${customerProductPlaceholder}'" loading="lazy" />
                    </a>
                </div>
                <div class="product-card-content">
                    <span class="product-card-category">${escapeHtml(product.category?.name || 'Uncategorized')}</span>
                    <h3 class="product-card-name">
                        <a href="/customer/products/${product.id}/" style="color: inherit; text-decoration: none;">${escapeHtml(product.name)}</a>
                    </h3>
                    <div class="product-card-pricing">
                        <span class="product-card-price">₦${formatCurrency(numericPrice)}</span>
                    </div>
                    <div class="product-card-stock stock-${status}">
                        ${formatStatus(status, product.stock?.quantity)}
                    </div>
                    <div class="product-card-actions">
                        <a href="/customer/products/${product.id}/" class="btn-card-view">View</a>
                        <button
                            type="button"
                            class="btn-card-add"
                            data-product-id="${product.id}"
                            ${isOutOfStock ? 'disabled style="opacity: 0.6; cursor: not-allowed;"' : ''}
                        >
                            <i class="bi bi-cart-plus"></i> ${isOutOfStock ? 'Sold Out' : 'Add'}
                        </button>
                    </div>
                </div>
            </article>
        `);    });

    grid.innerHTML = renderedCards.join('');

    // Attach event listeners to Add buttons
    grid.querySelectorAll('button[data-product-id]').forEach(button => {
        button.addEventListener('click', async () => {
            const product = products.find(item => String(item.id) === button.dataset.productId);
            if (!product) return;

            button.disabled = true;
            const originalHTML = button.innerHTML;
            button.innerHTML = '<i class="bi bi-arrow-repeat"></i> Adding…';
            const added = await addProductToCart(product, 1);
            button.innerHTML = added ? '<i class="bi bi-check2"></i> Added' : originalHTML;

            setTimeout(() => {
                button.disabled = false;
                button.innerHTML = originalHTML;
            }, 1800);
        });
    });

    updateSummary(response.data?.pagination?.total_count || products.length);
    announceProductResults(`${response.data?.pagination?.total_count || products.length} products found. Page ${customerProductState.page}.`);
}

function syncCatalogUrl(query, category, stock, sort) {
    const url = new URL(window.location.href);
    const values = { q: query, category, stock, sort_by: sort, page: customerProductState.page };
    Object.entries(values).forEach(([key, value]) => {
        if (!value || (key === 'stock' && value === 'all') || (key === 'sort_by' && value === 'name') || (key === 'page' && value === 1)) {
            url.searchParams.delete(key);
        } else {
            url.searchParams.set(key, String(value));
        }
    });
    url.searchParams.delete('search');
    url.searchParams.delete('format');
    window.history.replaceState({}, '', url);
}

function announceProductResults(message) {
    const status = document.getElementById('productResultsStatus');
    if (status) status.textContent = message;
}

async function loadCategories() {
    const select = document.getElementById('customerCategoryFilter');
    const pillsWrap = document.getElementById('categoryPillsWrap');
    if (!select) return;

    const response = await apiRequest('/customer/products/?format=json&page_size=1');
    if (!response.success) return;

    const categories = response.data?.categories || [];

    // Populate Select Options
    const selected = select.value;
    select.replaceChildren(new Option('All categories', 'all'));
    categories.forEach(category => select.add(new Option(category.name, category.slug)));
    if (customerProductState.activeCategory && customerProductState.activeCategory !== 'all') {
        select.value = customerProductState.activeCategory;
    } else {
        select.value = selected || 'all';
    }

    // Populate Category Pills
    if (pillsWrap) {
        const pillsHtml = [
            `<button type="button" class="category-pill ${customerProductState.activeCategory === 'all' ? 'active' : ''}" data-category="all" aria-pressed="${customerProductState.activeCategory === 'all'}">
                <i class="bi bi-grid-fill"></i>
                <span>All Products</span>
            </button>`
        ];

        categories.forEach(cat => {
            const isActive = customerProductState.activeCategory === cat.slug;
            pillsHtml.push(`
                <button type="button" class="category-pill ${isActive ? 'active' : ''}" data-category="${cat.slug}" aria-pressed="${isActive}">
                    <span>${escapeHtml(cat.name)}</span>
                </button>
            `);
        });

        pillsWrap.innerHTML = pillsHtml.join('');

        pillsWrap.querySelectorAll('.category-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                const cat = pill.dataset.category || 'all';
                syncCategoryPill(cat);
                if (select) select.value = cat;
                customerProductState.page = 1;
                loadProducts();
            });
        });
    }
}

function getFilterValue(id) {
    const value = document.getElementById(id)?.value || '';
    return value === 'all' ? '' : value;
}

function normalizeStatus(status) {
    return String(status || 'OUT_OF_STOCK').toLowerCase().replaceAll('_', '-');
}

function formatStatus(status, quantity = 0) {
    const qty = Number(quantity || 0);
    if (qty <= 0 || status === 'out-of-stock') return 'Out of Stock';
    if (qty <= 5 || status === 'low-stock') return `Low Stock (${qty} left)`;
    return 'In Stock';
}

function updatePagination(pagination) {
    const page = pagination.page || customerProductState.page;
    const totalPages = pagination.total_pages || 1;
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

async function addProductToCart(product, quantity = 1) {
    const response = await apiRequest('/customer/cart/items/', {
        method: 'POST',
        body: {
            product_id: product.id,
            quantity: quantity,
            action: 'add',
        },
    });

    if (response.success) {
        updateCartCount(response.data?.item_count);
        if (typeof window.updateCustomerCartBadge === 'function') {
            window.updateCustomerCartBadge(response.data?.item_count);
        }
        return true;
    } else {
        if (response.status === 401) {
            window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
            return;
        }
        const errorMsg = response.message || (response.errors ? Object.values(response.errors).flat().join('\n') : 'Unable to add product to cart.');
        alert(errorMsg);
        return false;
    }
}

async function updateCartCount(count) {
    let totalCount = count;
    if (typeof totalCount !== 'number') {
        const response = await apiRequest('/customer/cart/?format=json');
        if (response.success && response.data) {
            totalCount = response.data.item_count || 0;
        } else {
            totalCount = 0;
        }
    }

    const badge = document.getElementById('cartItemCount');
    if (badge) badge.replaceChildren(document.createTextNode(String(totalCount)));

    const summaryCount = document.getElementById('cartSummaryItemCount');
    if (summaryCount) summaryCount.replaceChildren(document.createTextNode(`${totalCount} items`));

    if (typeof window.updateCustomerCartBadge === 'function') {
        window.updateCustomerCartBadge(totalCount);
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
