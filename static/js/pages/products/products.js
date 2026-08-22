/** MADAM HY - Products catalog interactions. */

const productListState = { page: 1, pageSize: 10, requestId: 0 };
const productPlaceholder = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

document.addEventListener("DOMContentLoaded", () => {
    if (!canManageProducts()) document.getElementById("addProductLink")?.remove();
    setupProductFilters();
    loadCategories();
    loadProducts();
    setupViewToggle();
    setupPagination();
});

function setupProductFilters() {
    const search = document.getElementById("productSearch");
    const categoryFilter = document.getElementById("categoryFilter");
    const stockFilter = document.getElementById("stockFilter");
    const sortSelect = document.getElementById("sortSelect");

    const applyFilters = () => {
        productListState.page = 1;
        loadProducts();
    };

    let searchTimer;
    search?.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(applyFilters, 300);
    });
    categoryFilter?.addEventListener("change", applyFilters);
    stockFilter?.addEventListener("change", applyFilters);
    sortSelect?.addEventListener("change", applyFilters);
}

function setupViewToggle() {
    const toggleBtn = document.getElementById("toggleViewBtn");
    const grid = document.getElementById("productGrid");

    if (!toggleBtn || !grid) return;

    let gridMode = true;

    toggleBtn.addEventListener("click", () => {
        gridMode = !gridMode;
        grid.classList.toggle("product-list-view", !gridMode);
        toggleBtn.textContent = gridMode ? "Grid view" : "List view";
    });
}

function setupPagination() {
    document.getElementById("productsPrevious")?.addEventListener("click", () => {
        if (productListState.page > 1) {
            productListState.page -= 1;
            loadProducts();
        }
    });
    document.getElementById("productsNext")?.addEventListener("click", () => {
        productListState.page += 1;
        loadProducts();
    });
}

async function loadProducts() {
    const grid = document.getElementById("productGrid");
    const emptyState = document.getElementById("productEmptyState");
    if (!grid) return;

    const params = new URLSearchParams({
        page: String(productListState.page),
        page_size: String(productListState.pageSize),
        search: document.getElementById("productSearch")?.value.trim() || "",
        category: getFilterValue("categoryFilter"),
        stock: getFilterValue("stockFilter"),
        sort_by: document.getElementById("sortSelect")?.value || "name"
    });
    ["search", "category", "stock"].forEach(key => {
        if (!params.get(key)) params.delete(key);
    });

    const requestId = ++productListState.requestId;
    setProductStatus("Loading products...", false);
    const response = await apiRequest(`/products/?${params.toString()}`);
    if (requestId !== productListState.requestId) return;

    if (!response.success) {
        grid.replaceChildren();
        emptyState?.classList.add("empty-state-hidden");
        setProductStatus(response.message || "Unable to load products.", true, loadProducts);
        return;
    }

    const products = response.data?.products || [];
    const pagination = response.data?.pagination || {};
    renderProductCards(products);
    updateSummary(pagination.total_count || 0, products);
    updatePagination(pagination);
    setProductStatus("", false);
}

function renderProductCards(products) {
    const grid = document.getElementById("productGrid");
    const emptyState = document.getElementById("productEmptyState");
    if (!grid) return;

    if (!products.length) {
        grid.replaceChildren();
        emptyState?.classList.remove("empty-state-hidden");
        return;
    }

    emptyState?.classList.add("empty-state-hidden");
    grid.innerHTML = products.map(product => {
        const status = normalizeStatus(product.stock?.status);
        const category = product.category?.name || "Uncategorised";
        const image = product.image?.url || productPlaceholder;
        return `
        <article class="product-card" aria-label="${product.name}">
            <div class="product-card-image">
                <img src="${image}" alt="${product.image?.alt_text || product.name}" onerror="this.src='${productPlaceholder}'" />
            </div>

            <div class="product-card-content">
                <div class="product-card-top">
                    <span class="product-category">${category}</span>
                    <span class="stock-pill stock-${status}">${formatStatus(status)}</span>
                </div>

                <h3>${product.name}</h3>
                <p>${product.description || "No description available."}</p>

                <div class="product-card-meta">
                    <span class="product-price">₦ ${formatCurrency(product.selling_price)}</span>
                    <span class="product-stock">${product.stock?.quantity ?? 0} units</span>
                </div>

                <div class="product-card-actions">
                    <a href="/preview/products/detail/?id=${product.id}" class="btn btn-outline btn-sm">View</a>
                </div>
            </div>
        </article>
    `;
    }).join("");
}

async function loadCategories() {
    const select = document.getElementById("categoryFilter");
    if (!select) return;
    const response = await apiRequest("/products/categories/");
    if (!response.success) return;
    const selected = select.value;
    select.replaceChildren(new Option("All categories", "all"));
    const categories = response.data?.categories || [];
    categories.forEach(category => {
        select.add(new Option(category.name, category.slug));
    });
    select.value = selected;
    document.getElementById("categoryCount")?.replaceChildren(document.createTextNode(String(categories.length)));
}

function getFilterValue(id) {
    const value = document.getElementById(id)?.value || "";
    return value === "all" ? "" : value;
}

function normalizeStatus(status) {
    return String(status || "OUT_OF_STOCK").toLowerCase().replaceAll("_", "-");
}

function formatStatus(status) {
    if (status === "in-stock") return "In stock";
    if (status === "low-stock") return "Low stock";
    return "Out of stock";
}

function formatCurrency(value) {
    return Number(value).toLocaleString("en-NG");
}

function updateSummary(total, products) {
    document.getElementById("totalProducts")?.replaceChildren(document.createTextNode(String(total)));
    document.getElementById("inStockCount")?.replaceChildren(document.createTextNode(String(products.filter(product => normalizeStatus(product.stock?.status) === "in-stock").length)));
    document.getElementById("lowStockCount")?.replaceChildren(document.createTextNode(String(products.filter(product => normalizeStatus(product.stock?.status) === "low-stock").length)));
}

function updatePagination(pagination) {
    const page = pagination.page || productListState.page;
    const totalPages = pagination.total_pages || 0;
    productListState.page = page;
    const previous = document.getElementById("productsPrevious");
    const next = document.getElementById("productsNext");
    if (previous) previous.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages || totalPages === 0;
    document.getElementById("productsPage")?.replaceChildren(document.createTextNode(`Page ${page} of ${totalPages}`));
}

function setProductStatus(message, isError, retry) {
    const status = document.getElementById("productStatus");
    if (!status) return;
    status.replaceChildren();
    status.classList.toggle("empty-state-hidden", !message);
    if (!message) return;
    const text = document.createElement("p");
    text.textContent = message;
    status.append(text);
    if (isError && retry) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-secondary btn-sm";
        button.textContent = "Retry";
        button.addEventListener("click", retry);
        status.append(button);
    }
}
