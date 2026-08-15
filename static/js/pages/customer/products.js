/**
 * MADAM HY - Customer Products Browsing
 * Frontend-only product catalog for customers
 */

const customerProductsData = [
    {
        id: 1,
        name: "Green Ankara Fabric Premium",
        category: "Fashion",
        price: 12500,
        stock: 24,
        status: "in-stock",
        description: "Premium quality Ankara fabric designed for statement tailoring.",
        image: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 2,
        name: "Velvet Evening Gown",
        category: "Fashion",
        price: 28000,
        stock: 7,
        status: "low-stock",
        description: "Elegant evening wear with a smooth finish.",
        image: "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 3,
        name: "Radiant Glow Serum",
        category: "Beauty",
        price: 9500,
        stock: 18,
        status: "in-stock",
        description: "A lightweight skincare serum for brighter complexion.",
        image: "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 4,
        name: "Kitchen Storage Basket",
        category: "Home",
        price: 6200,
        stock: 3,
        status: "low-stock",
        description: "Organised storage for kitchens and shelves.",
        image: "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 5,
        name: "Wireless Speaker Mini",
        category: "Electronics",
        price: 22000,
        stock: 0,
        status: "out-of-stock",
        description: "Compact wireless speaker with rich sound.",
        image: "https://images.unsplash.com/photo-1518444065439-e933c06ce9cd?auto=format&fit=crop&w=900&q=80"
    },
    {
        id: 6,
        name: "Leather Office Tote",
        category: "Fashion",
        price: 18500,
        stock: 15,
        status: "in-stock",
        description: "Smart office accessory that combines durability.",
        image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=80"
    }
];

let customerCart = [];

document.addEventListener('DOMContentLoaded', () => {
    setupFilters();
    renderProducts();
    updateCartCount();
});

function setupFilters() {
    const search = document.getElementById('customerProductSearch');
    const category = document.getElementById('customerCategoryFilter');
    const stock = document.getElementById('customerStockFilter');
    const sort = document.getElementById('customerSortSelect');

    const applyFilters = () => renderProducts();
    search?.addEventListener('input', applyFilters);
    category?.addEventListener('change', applyFilters);
    stock?.addEventListener('change', applyFilters);
    sort?.addEventListener('change', applyFilters);
}

function renderProducts() {
    const grid = document.getElementById('customerProductGrid');
    const empty = document.getElementById('customerProductsEmpty');
    if (!grid) return;

    const searchValue = document.getElementById('customerProductSearch')?.value.toLowerCase() || '';
    const categoryFilter = document.getElementById('customerCategoryFilter')?.value || 'all';
    const stockFilter = document.getElementById('customerStockFilter')?.value || 'all';
    const sortValue = document.getElementById('customerSortSelect')?.value || 'name';

    let filtered = customerProductsData.filter(item => {
        const matchesSearch = !searchValue || item.name.toLowerCase().includes(searchValue);
        const matchesCategory = categoryFilter === 'all' || item.category === categoryFilter;
        const matchesStock = stockFilter === 'all' || item.status === stockFilter || (stockFilter === 'low-stock' && item.stock < 10 && item.stock > 0);
        return matchesSearch && matchesCategory && matchesStock;
    });

    if (sortValue === 'price-high') {
        filtered.sort((a, b) => b.price - a.price);
    } else if (sortValue === 'price-low') {
        filtered.sort((a, b) => a.price - b.price);
    } else {
        filtered.sort((a, b) => a.name.localeCompare(b.name));
    }

    if (!filtered.length) {
        grid.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        updateSummary(0);
        return;
    }

    empty?.classList.add('empty-state-hidden');
    grid.innerHTML = filtered.map(product => `
        <div class="customer-product-card">
            <div class="product-card-image">
                <img src="${product.image}" alt="${product.name}" />
            </div>
            <div class="product-card-content">
                <span class="product-card-category">${product.category}</span>
                <h3 class="product-card-name">${product.name}</h3>
                <div class="product-card-price">₦${formatCurrency(product.price)}</div>
                <div class="product-card-stock">${product.status === 'in-stock' ? 'In stock' : product.status === 'low-stock' ? `Low stock (${product.stock} left)` : 'Out of stock'}</div>
                <div class="product-card-actions">
                    <a href="/customer/product/${product.id}/" class="btn btn-secondary btn-sm">View</a>
                    <button type="button" class="btn btn-primary btn-sm" onclick="addProductToCart(${product.id}, '${product.name}', ${product.price})">Add</button>
                </div>
            </div>
        </div>
    `).join('');

    updateSummary(filtered.length);
}

function updateSummary(count) {
    document.getElementById('availableProductsCount')?.replaceChildren(document.createTextNode(String(count)));
}

function addProductToCart(id, name, price) {
    const existing = customerCart.find(item => item.id === id);
    if (existing) {
        existing.quantity += 1;
    } else {
        customerCart.push({ id, name, price, quantity: 1 });
    }
    updateCartCount();
    alert(`${name} added to cart!`);
}

function updateCartCount() {
    const count = customerCart.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('cartItemCount')?.replaceChildren(document.createTextNode(String(count)));
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
