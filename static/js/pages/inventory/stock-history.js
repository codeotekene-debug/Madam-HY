/**
 * MADAM HY - Stock history API integration.
 * Read-only movement history backed by the Inventory API.
 */

const stockHistoryState = {
    inventory: [],
    selectedInventoryId: null,
    page: 1,
    pageSize: 10,
};

document.addEventListener("DOMContentLoaded", () => {
    setupStockHistoryControls();
    loadInventoryOptions();
});

function setupStockHistoryControls() {
    document.getElementById("stockHistoryRetryButton")?.addEventListener("click", () => loadInventoryOptions());
    document.getElementById("stockHistoryErrorRetryButton")?.addEventListener("click", () => loadInventoryOptions());
    document.getElementById("stockHistoryInventorySelect")?.addEventListener("change", event => {
        stockHistoryState.selectedInventoryId = Number(event.target.value) || null;
        stockHistoryState.page = 1;
        if (stockHistoryState.selectedInventoryId) {
            loadStockHistory();
        }
    });
}

async function loadInventoryOptions() {
    const select = document.getElementById("stockHistoryInventorySelect");
    const tableBody = document.getElementById("stockHistoryTableBody");

    showStockHistoryError("");
    showStockHistoryEmpty(false);
    if (select) select.innerHTML = `<option value="">Loading inventory...</option>`;
    if (tableBody) tableBody.innerHTML = loadingRow("Loading inventory...", 8);

    const response = await apiRequest("/inventory/?page_size=100&sort_by=product_name");
    if (!response.success) {
        if (select) select.innerHTML = `<option value="">Inventory unavailable</option>`;
        if (tableBody) tableBody.innerHTML = "";
        showStockHistoryError(response.message || "Inventory could not load.");
        return;
    }

    stockHistoryState.inventory = response.data?.inventory || [];
    renderInventorySelect();

    if (!stockHistoryState.inventory.length) {
        if (tableBody) tableBody.innerHTML = "";
        showStockHistoryEmpty(true);
        return;
    }

    stockHistoryState.selectedInventoryId = stockHistoryState.inventory[0].id;
    if (select) select.value = String(stockHistoryState.selectedInventoryId);
    loadStockHistory();
}

async function loadStockHistory() {
    const tableBody = document.getElementById("stockHistoryTableBody");
    if (!tableBody || !stockHistoryState.selectedInventoryId) return;

    showStockHistoryError("");
    showStockHistoryEmpty(false);
    tableBody.innerHTML = loadingRow("Loading stock history...", 8);

    const query = new URLSearchParams({
        page: String(stockHistoryState.page),
        page_size: String(stockHistoryState.pageSize),
    });
    const response = await apiRequest(`/inventory/${stockHistoryState.selectedInventoryId}/movements/?${query.toString()}`);

    if (!response.success) {
        tableBody.innerHTML = "";
        renderPagination(null);
        showStockHistoryError(response.message || "Stock history could not load.");
        return;
    }

    const movements = response.data?.movements || [];
    renderStockHistory(response.data?.inventory, movements);
    renderPagination(response.data?.pagination || null);
}

function renderInventorySelect() {
    const select = document.getElementById("stockHistoryInventorySelect");
    if (!select) return;

    if (!stockHistoryState.inventory.length) {
        select.innerHTML = `<option value="">No inventory found</option>`;
        return;
    }

    select.innerHTML = stockHistoryState.inventory.map(item => {
        const product = item.product || {};
        return `<option value="${item.id}">${escapeHtml(product.name || "Unknown product")} (${escapeHtml(item.sku || product.sku || "-")})</option>`;
    }).join("");
}

function renderStockHistory(inventoryItem, movements) {
    const tableBody = document.getElementById("stockHistoryTableBody");
    if (!tableBody) return;

    if (!movements.length) {
        tableBody.innerHTML = "";
        showStockHistoryEmpty(true);
        return;
    }

    const productName = inventoryItem?.product?.name || "Unknown product";
    showStockHistoryEmpty(false);
    tableBody.innerHTML = movements.map(item => {
        const movementClass = movementPillClass(item.quantity);
        return `
            <tr>
                <td data-label="Date">${formatDateTime(item.created_at)}</td>
                <td data-label="Product"><strong>${escapeHtml(productName)}</strong></td>
                <td data-label="Movement"><span class="movement-pill ${movementClass}">${formatDelta(item.quantity)} ${escapeHtml(formatMovementType(item.movement_type))}</span></td>
                <td data-label="Previous">${formatNumber(item.previous_quantity)}</td>
                <td data-label="New">${formatNumber(item.new_quantity)}</td>
                <td data-label="Reason">${escapeHtml(item.reason || "-")}</td>
                <td data-label="Reference">${escapeHtml(item.reference || "-")}</td>
                <td data-label="Created by">${escapeHtml(formatUser(item.created_by))}</td>
            </tr>
        `;
    }).join("");
}

function renderPagination(pagination) {
    const container = document.getElementById("stockHistoryPagination");
    if (!container) return;

    if (!pagination || pagination.total_pages <= 1) {
        container.innerHTML = "";
        return;
    }

    const previousPage = Math.max(1, pagination.page - 1);
    const nextPage = Math.min(pagination.total_pages, pagination.page + 1);
    container.innerHTML = `
        <button type="button" class="btn btn-secondary" data-page="${previousPage}" ${pagination.page <= 1 ? "disabled" : ""}>Previous</button>
        <span>Page ${pagination.page} of ${pagination.total_pages}</span>
        <button type="button" class="btn btn-secondary" data-page="${nextPage}" ${pagination.page >= pagination.total_pages ? "disabled" : ""}>Next</button>
    `;

    container.querySelectorAll("[data-page]").forEach(button => {
        button.addEventListener("click", () => {
            stockHistoryState.page = Number(button.dataset.page);
            loadStockHistory();
        });
    });
}

function showStockHistoryError(message) {
    const errorState = document.getElementById("stockHistoryErrorState");
    const errorMessage = document.getElementById("stockHistoryErrorMessage");
    if (!errorState) return;

    if (!message) {
        errorState.classList.add("inventory-state-hidden");
        return;
    }

    if (errorMessage) errorMessage.textContent = message;
    errorState.classList.remove("inventory-state-hidden");
}

function showStockHistoryEmpty(show) {
    document.getElementById("stockHistoryEmptyState")?.classList.toggle("empty-state-hidden", !show);
}

function loadingRow(message, colspan) {
    return `<tr><td colspan="${colspan}">${escapeHtml(message)}</td></tr>`;
}

function movementPillClass(quantity) {
    const value = Number(quantity || 0);
    if (value > 0) return "movement-in";
    if (value < 0) return "movement-out";
    return "movement-adjustment";
}

function formatMovementType(value) {
    return String(value || "-").replaceAll("_", " ").toLowerCase().replace(/\b\w/g, char => char.toUpperCase());
}

function formatDelta(value) {
    const number = Number(value || 0);
    return number > 0 ? `+${formatNumber(number)}` : formatNumber(number);
}

function formatUser(user) {
    if (!user) return "-";
    return user.full_name || user.username || user.email || "-";
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString("en-NG");
}

function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString("en-NG", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
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
