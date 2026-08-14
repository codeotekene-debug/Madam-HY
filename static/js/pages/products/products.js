/**
 * MADAM HY - Products list interactions.
 * Frontend-only demo data for product browsing and filtering.
 */

const productsData = [
    {
        id: 1,
        name: "Green Ankara Fabric Premium",
        category: "Fashion",
        price: 12500,
        stock: 24,
        status: "in-stock",
        description: "Premium quality Ankara fabric designed for statement tailoring and event wear.",
        image: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 2,
        name: "Velvet Evening Gown",
        category: "Fashion",
        price: 28000,
        stock: 7,
        status: "low-stock",
        description: "Elegant evening wear with a smooth finish, ideal for special occasions.",
        image: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 3,
        name: "Radiant Glow Serum",
        category: "Beauty",
        price: 9500,
        stock: 18,
        status: "in-stock",
        description: "A lightweight skincare serum for a brighter and more refreshed complexion.",
        image: "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 4,
        name: "Kitchen Storage Basket",
        category: "Home",
        price: 6200,
        stock: 3,
        status: "low-stock",
        description: "Organised storage for kitchens, shelves and compact living spaces.",
        image: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 5,
        name: "Wireless Speaker Mini",
        category: "Electronics",
        price: 22000,
        stock: 0,
        status: "out-of-stock",
        description: "Compact wireless speaker with rich sound and Bluetooth connectivity.",
        image: "https://images.unsplash.com/photo-1518444065439-e933c06ce9cd?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 6,
        name: "Leather Office Tote",
        category: "Fashion",
        price: 18500,
        stock: 15,
        status: "in-stock",
        description: "Smart office accessory that combines durability and a polished look.",
        image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=80"
    }
];

document.addEventListener("DOMContentLoaded", () => {
    setupProductFilters();
    renderProductCards();
    setupViewToggle();
});

function setupProductFilters() {
    const search = document.getElementById("productSearch");
    const categoryFilter = document.getElementById("categoryFilter");
    const stockFilter = document.getElementById("stockFilter");
    const sortSelect = document.getElementById("sortSelect");

    const applyFilters = () => renderProductCards();

    search?.addEventListener("input", applyFilters);
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

function renderProductCards() {
    const grid = document.getElementById("productGrid");
    const emptyState = document.getElementById("productEmptyState");
    const search = document.getElementById("productSearch");
    const categoryFilter = document.getElementById("categoryFilter");
    const stockFilter = document.getElementById("stockFilter");
    const sortSelect = document.getElementById("sortSelect");

    if (!grid) return;

    const query = search?.value.trim().toLowerCase() || "";
    const categoryValue = categoryFilter?.value || "all";
    const stockValue = stockFilter?.value || "all";
    const sortValue = sortSelect?.value || "name";

    let filteredProducts = productsData.filter(product => {
        const matchesQuery = !query || [
            product.name,
            product.category,
            product.description
        ].some(value => value.toLowerCase().includes(query));

        const matchesCategory = categoryValue === "all" || product.category === categoryValue;
        const matchesStock = stockValue === "all" || product.status === stockValue;

        return matchesQuery && matchesCategory && matchesStock;
    });

    filteredProducts = [...filteredProducts].sort((a, b) => {
        if (sortValue === "price-high") return b.price - a.price;
        if (sortValue === "price-low") return a.price - b.price;
        if (sortValue === "stock") return b.stock - a.stock;
        return a.name.localeCompare(b.name);
    });

    const totalProducts = document.getElementById("totalProducts");
    const inStockCount = document.getElementById("inStockCount");
    const lowStockCount = document.getElementById("lowStockCount");
    const categoryCount = document.getElementById("categoryCount");

    if (totalProducts) totalProducts.textContent = String(productsData.length);
    if (inStockCount) inStockCount.textContent = String(productsData.filter(p => p.status === "in-stock").length);
    if (lowStockCount) lowStockCount.textContent = String(productsData.filter(p => p.status === "low-stock").length);
    if (categoryCount) categoryCount.textContent = String(new Set(productsData.map(p => p.category)).size);

    if (!filteredProducts.length) {
        grid.innerHTML = "";
        emptyState?.classList.remove("empty-state-hidden");
        return;
    }

    emptyState?.classList.add("empty-state-hidden");
    grid.innerHTML = filteredProducts.map(product => `
        <article class="product-card" aria-label="${product.name}">
            <div class="product-card-image">
                <img src="${product.image}" alt="${product.name}" />
            </div>

            <div class="product-card-content">
                <div class="product-card-top">
                    <span class="product-category">${product.category}</span>
                    <span class="stock-pill stock-${product.status}">${formatStatus(product.status)}</span>
                </div>

                <h3>${product.name}</h3>
                <p>${product.description}</p>

                <div class="product-card-meta">
                    <span class="product-price">₦ ${formatCurrency(product.price)}</span>
                    <span class="product-stock">${product.stock} units</span>
                </div>

                <div class="product-card-actions">
                    <a href="#" class="btn btn-outline btn-sm">View</a>
                    <a href="#" class="btn btn-primary btn-sm">Edit</a>
                </div>
            </div>
        </article>
    `).join("");
}

function formatStatus(status) {
    if (status === "in-stock") return "In stock";
    if (status === "low-stock") return "Low stock";
    return "Out of stock";
}

function formatCurrency(value) {
    return Number(value).toLocaleString("en-NG");
}
