/**
 * MADAM HY - Low stock API integration.
 * Read-only view of low and out-of-stock inventory items.
 */

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("lowStockRetryButton")?.addEventListener("click", () => loadLowStock());
    document.getElementById("lowStockErrorRetryButton")?.addEventListener("click", () => loadLowStock());
    loadLowStock();
});

async function loadLowStock() {
    const list = document.getElementById("lowStockList");
    if (!list) return;

    showLowStockError("");
    showLowStockEmpty(false);
    list.innerHTML = `<div class="low-stock-item"><div class="low-stock-item-main"><strong>Loading low-stock inventory...</strong></div></div>`;

    const lowStockResponse = await apiRequest("/inventory/?stock_status=LOW_STOCK&page_size=100&sort_by=quantity_asc");
    const outOfStockResponse = await apiRequest("/inventory/?stock_status=OUT_OF_STOCK&page_size=100&sort_by=quantity_asc");

    if (!lowStockResponse.success || !outOfStockResponse.success) {
        list.innerHTML = "";
        renderLowStockSummary([]);
        showLowStockError(lowStockResponse.message || outOfStockResponse.message || "Low-stock inventory could not load.");
        return;
    }

    const items = [
        ...(outOfStockResponse.data?.inventory || []),
        ...(lowStockResponse.data?.inventory || []),
    ];

    renderLowStockSummary(items);
    renderLowStock(items);
}

function renderLowStockSummary(items) {
    const criticalCount = document.getElementById("criticalCount");
    const warningCount = document.getElementById("warningCount");
    const reorderQueue = document.getElementById("reorderQueue");

    if (criticalCount) criticalCount.textContent = String(items.filter(item => item.is_out_of_stock).length);
    if (warningCount) warningCount.textContent = String(items.filter(item => item.is_low_stock).length);
    if (reorderQueue) reorderQueue.textContent = String(items.length);
}

function renderLowStock(items) {
    const list = document.getElementById("lowStockList");
    if (!list) return;

    if (!items.length) {
        list.innerHTML = "";
        showLowStockEmpty(true);
        return;
    }

    showLowStockEmpty(false);
    list.innerHTML = items.map(item => {
        const product = item.product || {};
        const category = product.category || {};
        const level = item.is_out_of_stock ? "critical" : "warning";
        return `
            <div class="low-stock-item">
                <div class="low-stock-item-main">
                    <strong>${escapeHtml(product.name || "Unknown product")}</strong>
                    <span class="low-stock-meta">${escapeHtml(category.name || "Uncategorised")} - SKU: ${escapeHtml(item.sku || product.sku || "-")} - On hand: ${formatNumber(item.quantity)} - Reorder: ${formatNumber(item.reorder_level)}</span>
                </div>
                <span class="low-stock-level level-${level}">${level === "critical" ? "Critical" : "Warning"}</span>
            </div>
        `;
    }).join("");
}

function showLowStockError(message) {
    const errorState = document.getElementById("lowStockErrorState");
    const errorMessage = document.getElementById("lowStockErrorMessage");
    if (!errorState) return;

    if (!message) {
        errorState.classList.add("inventory-state-hidden");
        return;
    }

    if (errorMessage) errorMessage.textContent = message;
    errorState.classList.remove("inventory-state-hidden");
}

function showLowStockEmpty(show) {
    document.getElementById("lowStockEmptyState")?.classList.toggle("empty-state-hidden", !show);
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString("en-NG");
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    }[char]));
}
