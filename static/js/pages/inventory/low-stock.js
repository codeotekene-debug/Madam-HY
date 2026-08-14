/**
 * MADAM HY - Low stock interactions.
 * Frontend-only overview of products approaching reorder thresholds.
 */

const lowStockData = [
    {
        name: "Velvet Evening Gown",
        sku: "MH-GOW-22",
        category: "Fashion",
        onHand: 7,
        reorderLevel: 10,
        level: "warning"
    },
    {
        name: "Kitchen Storage Basket",
        sku: "MH-HOM-15",
        category: "Home",
        onHand: 3,
        reorderLevel: 8,
        level: "critical"
    },
    {
        name: "Wireless Speaker Mini",
        sku: "MH-ELE-41",
        category: "Electronics",
        onHand: 0,
        reorderLevel: 5,
        level: "critical"
    }
];

document.addEventListener("DOMContentLoaded", () => {
    renderLowStock();
});

function renderLowStock() {
    const list = document.getElementById("lowStockList");
    const criticalCount = document.getElementById("criticalCount");
    const warningCount = document.getElementById("warningCount");
    const reorderQueue = document.getElementById("reorderQueue");

    if (!list) return;

    if (criticalCount) criticalCount.textContent = String(lowStockData.filter(item => item.level === "critical").length);
    if (warningCount) warningCount.textContent = String(lowStockData.filter(item => item.level === "warning").length);
    if (reorderQueue) reorderQueue.textContent = String(lowStockData.length);

    list.innerHTML = lowStockData.map(item => `
        <div class="low-stock-item">
            <div class="low-stock-item-main">
                <strong>${item.name}</strong>
                <span class="low-stock-meta">${item.category} · SKU: ${item.sku} · On hand: ${item.onHand} · Reorder: ${item.reorderLevel}</span>
            </div>
            <span class="low-stock-level level-${item.level}">${item.level === "critical" ? "Critical" : "Warning"}</span>
        </div>
    `).join("");
}
