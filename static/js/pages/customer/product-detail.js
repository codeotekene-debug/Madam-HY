/**
 * MADAM HY - Customer Product Detail
 * Product detail view for customers
 */

const allProducts = [
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

let currentProduct = null;

document.addEventListener('DOMContentLoaded', () => {
    const productId = getProductIdFromUrl();
    currentProduct = allProducts.find(p => p.id === productId) || allProducts[0];
    renderDetail();
    bindActions();
});

function renderDetail() {
    if (!currentProduct) return;

    document.getElementById('productImage')?.setAttribute('src', currentProduct.image);
    document.getElementById('productImage')?.setAttribute('alt', currentProduct.name);
    document.getElementById('productName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('productCategory')?.replaceChildren(document.createTextNode(currentProduct.category));
    document.getElementById('productPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(currentProduct.price)}`));
    document.getElementById('productDescription')?.replaceChildren(document.createTextNode(currentProduct.description));
    document.getElementById('productStockStatus')?.replaceChildren(document.createTextNode(getStockStatus(currentProduct.status)));
    document.getElementById('productStockStatus')?.className = `detail-stock status-${currentProduct.status}`;

    document.getElementById('detailName')?.replaceChildren(document.createTextNode(currentProduct.name));
    document.getElementById('detailCategory')?.replaceChildren(document.createTextNode(currentProduct.category));
    document.getElementById('detailPrice')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(currentProduct.price)}`));
    document.getElementById('detailStock')?.replaceChildren(document.createTextNode(`${currentProduct.stock} available`));

    if (currentProduct.status === 'out-of-stock') {
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
        e.target.value = Math.max(1, Math.min(value, currentProduct.stock));
    });

    decrement?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        quantityInput!.value = String(Math.max(1, current - 1));
    });

    increment?.addEventListener('click', () => {
        const current = parseInt(quantityInput?.value) || 1;
        quantityInput!.value = String(Math.min(current + 1, currentProduct.stock));
    });

    addBtn?.addEventListener('click', () => {
        const quantity = parseInt(quantityInput?.value || '1');
        const successAlert = document.getElementById('productSuccessAlert');
        if (successAlert) {
            successAlert.textContent = `${quantity} × ${currentProduct.name} added to cart!`;
            successAlert.classList.remove('hidden');
            setTimeout(() => {
                successAlert.classList.add('hidden');
            }, 3000);
        }
        quantityInput!.value = '1';
    });

    continueBtn?.addEventListener('click', () => {
        window.location.href = '/customer/products/';
    });
}

function getProductIdFromUrl() {
    return parseInt(window.location.pathname.split('/')[3]) || 1;
}

function getStockStatus(status) {
    switch (status) {
        case 'in-stock':
            return 'In stock';
        case 'low-stock':
            return 'Low stock';
        case 'out-of-stock':
            return 'Out of stock';
        default:
            return status;
    }
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
