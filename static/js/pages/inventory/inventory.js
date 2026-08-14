/**
 * MADAM HY - Inventory overview interactions.
 * Frontend-only demo data for stock monitoring and filtering.
 */

const inventoryData = [
    {
        name: "Green Ankara Fabric Premium",
        category: "Fashion",
        sku: "MH-FAB-104",
        onHand: 24,
        reorderLevel: 8,
        unitPrice: 12500,
        status: "in-stock"
    },
    {
        name: "Velvet Evening Gown",
        category: "Fashion",
        sku: "MH-GOW-22",
        onHand: 7,
        reorderLevel: 10,
        unitPrice: 28000,
        status: "low-stock"
    },
    {
        name: "Radiant Glow Serum",
        category: "Beauty",
        sku: "MH-BEA-58",
        onHand: 18,
        reorderLevel: 6,
        unitPrice: 9500,
        status: "in-stock"
    },
    {
        name: "Kitchen Storage Basket",
        category: "Home",
        sku: "MH-HOM-15",
        onHand: 3,
        reorderLevel: 8,
        unitPrice: 6200,
        status: "low-stock"
    },
    {
        name: "Wireless Speaker Mini",
        category: "Electronics",
        sku: "MH-ELE-41",
        onHand: 0,
        reorderLevel: 5,
        unitPrice: 22000,
        status: "out-of-stock"
    },
    {
        name: "Leather Office Tote",
        category: "Fashion",
        sku: "MH-ACC-77",
        onHand: 15,
        reorderLevel: 6,
        unitPrice: 18500,
        status: "in-stock"
    }
];

document.addEventListener("DOMContentLoaded", () => {
    renderInventorySummary();
    renderInventoryTable();
    setupInventoryFilters();
});

function setupInventoryFilters() {
    const searchInput = document.getElementById("inventorySearch");
    const categoryFilter = document.getElementById("inventoryCategoryFilter");
    const statusFilter = document.getElementById("inventoryStatusFilter");
    const sortSelect = document.getElementById("inventorySort");

    const update = () => renderInventoryTable();

    searchInput?.addEventListener("input", update);
    categoryFilter?.addEventListener("change", update);
    statusFilter?.addEventListener("change", update);
    sortSelect?.addEventListener("change", update);
}

function renderInventorySummary() {
    const total = document.getElementById("totalInventoryItems");
    const stockValue = document.getElementById("stockValue");
    const lowStock = document.getElementById("lowStockCount");
    const outOfStock = document.getElementById("outOfStockCount");

    if (total) total.textContent = String(inventoryData.length);
    if (stockValue) stockValue.textContent = `₦ ${formatCurrency(inventoryData.reduce((sum, item) => sum + item.onHand * item.unitPrice, 0))}`;
    if (lowStock) lowStock.textContent = String(inventoryData.filter(item => item.status === "low-stock").length);
    if (outOfStock) outOfStock.textContent = String(inventoryData.filter(item => item.status === "out-of-stock").length);
}

function renderInventoryTable() {
    const tableBody = document.getElementById("inventoryTableBody");
    const emptyState = document.getElementById("inventoryEmptyState");
    const searchInput = document.getElementById("inventorySearch");
    const categoryFilter = document.getElementById("inventoryCategoryFilter");
    const statusFilter = document.getElementById("inventoryStatusFilter");
    const sortSelect = document.getElementById("inventorySort");

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || "";
    const categoryValue = categoryFilter?.value || "all";
    const statusValue = statusFilter?.value || "all";
    const sortValue = sortSelect?.value || "name";

    let filteredItems = inventoryData.filter(item => {
        const matchesQuery = !query || [item.name, item.category, item.sku].some(value => value.toLowerCase().includes(query));
        const matchesCategory = categoryValue === "all" || item.category === categoryValue;
        const matchesStatus = statusValue === "all" || item.status === statusValue;

        return matchesQuery && matchesCategory && matchesStatus;
    });

    filteredItems = [...filteredItems].sort((a, b) => {
        if (sortValue === "stock-high") return b.onHand - a.onHand;
        if (sortValue === "stock-low") return a.onHand - b.onHand;
        if (sortValue === "value-high") return (b.onHand * b.unitPrice) - (a.onHand * a.unitPrice);
        return a.name.localeCompare(b.name);
    });

    if (!filteredItems.length) {
        tableBody.innerHTML = "";
        emptyState?.classList.remove("empty-state-hidden");
        return;
    }

    emptyState?.classList.add("empty-state-hidden");
    tableBody.innerHTML = filteredItems.map(item => `
        <tr>
            <td data-label="Product"><strong>${item.name}</strong></td>
            <td data-label="Category">${item.category}</td>
            <td data-label="SKU">${item.sku}</td>
            <td data-label="On hand">${item.onHand}</td>
            <td data-label="Reorder">${item.reorderLevel}</td>
            <td data-label="Unit price">₦ ${formatCurrency(item.unitPrice)}</td>
            <td data-label="Stock value">₦ ${formatCurrency(item.onHand * item.unitPrice)}</td>
            <td data-label="Status"><span class="stock-status status-${item.status}">${formatStatus(item.status)}</span></td>
        </tr>
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
