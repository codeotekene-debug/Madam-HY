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

    const reportResponse = await apiRequest("/inventory/reports/low-stock/?page_size=100");

    if (reportResponse.success && reportResponse.data) {
        const data = reportResponse.data;
        const items = data.low_stock_products || data.items || [];
        renderLowStockSummaryFromApi(data);
        renderLowStock(items);
        return;
    }

    // Fallback if reports endpoint unavailable or unauthorized
    const lowStockResponse = await apiRequest("/inventory/?stock_status=LOW_STOCK&page_size=100&sort_by=quantity_asc");
    const outOfStockResponse = await apiRequest("/inventory/?stock_status=OUT_OF_STOCK&page_size=100&sort_by=quantity_asc");

    if (!lowStockResponse.success || !outOfStockResponse.success) {
        list.innerHTML = "";
        renderLowStockSummaryFallback([]);
        showLowStockError(reportResponse.message || lowStockResponse.message || outOfStockResponse.message || "Low-stock inventory could not load.");
        return;
    }

    const items = [
        ...(outOfStockResponse.data?.inventory || []),
        ...(lowStockResponse.data?.inventory || []),
    ];

    renderLowStockSummaryFallback(items);
    renderLowStock(items);
}

function renderLowStockSummaryFromApi(data) {
    const criticalCount = document.getElementById("criticalCount");
    const warningCount = document.getElementById("warningCount");
    const reorderQueue = document.getElementById("reorderQueue");

    if (criticalCount) criticalCount.textContent = formatNumber(data.critical_count ?? 0);
    if (warningCount) warningCount.textContent = formatNumber(data.warning_count ?? 0);
    if (reorderQueue) reorderQueue.textContent = formatNumber(data.total_low_stock ?? 0);
}

function renderLowStockSummaryFallback(items) {
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
        const level = (item.is_out_of_stock || item.urgency === "CRITICAL") ? "critical" : "warning";
        const shortage = item.shortage_amount !== undefined
            ? ` - Shortage: ${formatNumber(item.shortage_amount)} units`
            : "";
        return `
            <div class="low-stock-item">
                <div class="low-stock-item-main">
                    <strong>${escapeHtml(product.name || "Unknown product")}</strong>
                    <span class="low-stock-meta">${escapeHtml(category.name || "Uncategorised")} - SKU: ${escapeHtml(item.sku || product.sku || "-")} - On hand: ${formatNumber(item.quantity)} - Reorder: ${formatNumber(item.reorder_level)}${shortage}</span>
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
