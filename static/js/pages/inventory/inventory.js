/**
 * MADAM HY - Inventory overview API integration.
 * Read-only stock visibility backed by the Inventory API.
 */

const inventoryState = {
    page: 1,
    pageSize: 10,
    movementPage: 1,
    movementPageSize: 10,
    selectedInventoryId: null,
};

document.addEventListener("DOMContentLoaded", () => {
    setupInventoryFilters();
    setupInventoryActions();
    loadInventory();
});

function setupInventoryFilters() {
    const searchInput = document.getElementById("inventorySearch");
    const statusFilter = document.getElementById("inventoryStatusFilter");
    const sortSelect = document.getElementById("inventorySort");

    searchInput?.addEventListener("input", debounce(() => {
        inventoryState.page = 1;
        loadInventory();
    }, 250));

    statusFilter?.addEventListener("change", () => {
        inventoryState.page = 1;
        loadInventory();
    });

    sortSelect?.addEventListener("change", () => {
        inventoryState.page = 1;
        loadInventory();
    });
}

function setupInventoryActions() {
    document.getElementById("inventoryRetryButton")?.addEventListener("click", () => loadInventory());
    document.getElementById("inventoryErrorRetryButton")?.addEventListener("click", () => loadInventory());

    document.getElementById("inventoryTableBody")?.addEventListener("click", event => {
        const button = event.target.closest("[data-inventory-detail]");
        if (!button) return;

        const inventoryId = Number(button.dataset.inventoryDetail);
        if (!inventoryId) return;

        inventoryState.selectedInventoryId = inventoryId;
        inventoryState.movementPage = 1;
        loadInventoryDetail(inventoryId);
        loadInventoryMovements(inventoryId);
    });
}

async function loadInventory() {
    const tableBody = document.getElementById("inventoryTableBody");
    if (!tableBody) return;

    showInventoryError("");
    showInventoryEmpty(false);
    tableBody.innerHTML = loadingRow("Loading inventory...", 9);

    const response = await apiRequest(`/inventory/${buildInventoryQuery()}`);

    if (!response.success) {
        tableBody.innerHTML = "";
        renderInventorySummary([], null);
        renderPagination("inventoryPagination", null, () => {});
        showInventoryError(response.message || "Inventory could not load.");
        return;
    }

    const inventory = response.data?.inventory || [];
    const pagination = response.data?.pagination || null;

    renderInventorySummary(inventory, pagination);
    renderInventoryTable(inventory);
    renderPagination("inventoryPagination", pagination, page => {
        inventoryState.page = page;
        loadInventory();
    });
}

async function loadInventoryDetail(inventoryId) {
    const panel = document.getElementById("inventoryDetailPanel");
    const content = document.getElementById("inventoryDetailContent");
    const title = document.getElementById("inventoryDetailTitle");

    if (!panel || !content) return;

    panel.classList.remove("inventory-state-hidden");
    content.innerHTML = detailLoading();
    if (title) title.textContent = "Inventory detail";

    const response = await apiRequest(`/inventory/${inventoryId}/`);
    if (!response.success) {
        content.innerHTML = detailMetric("Error", response.message || "Detail could not load.");
        return;
    }

    const item = response.data;
    if (title) title.textContent = item.product?.name || "Inventory detail";
    content.innerHTML = renderInventoryDetail(item);
}

async function loadInventoryMovements(inventoryId) {
    const tableBody = document.getElementById("inventoryMovementTableBody");
    if (!tableBody) return;

    showMovementEmpty(false);
    tableBody.innerHTML = loadingRow("Loading movement history...", 8);

    const query = new URLSearchParams({
        page: String(inventoryState.movementPage),
        page_size: String(inventoryState.movementPageSize),
    });
    const response = await apiRequest(`/inventory/${inventoryId}/movements/?${query.toString()}`);

    if (!response.success) {
        tableBody.innerHTML = errorRow(response.message || "Movement history could not load.", 8);
        renderPagination("inventoryMovementPagination", null, () => {});
        return;
    }

    const movements = response.data?.movements || [];
    const pagination = response.data?.pagination || null;
    renderMovementTable(movements);
    renderPagination("inventoryMovementPagination", pagination, page => {
        inventoryState.movementPage = page;
        loadInventoryMovements(inventoryId);
    });
}

function buildInventoryQuery() {
    const search = document.getElementById("inventorySearch")?.value.trim() || "";
    const status = document.getElementById("inventoryStatusFilter")?.value || "all";
    const sortBy = document.getElementById("inventorySort")?.value || "product_name";
    const query = new URLSearchParams({
        page: String(inventoryState.page),
        page_size: String(inventoryState.pageSize),
        sort_by: sortBy,
    });

    if (search) query.set("search", search);
    if (status !== "all") query.set("stock_status", status);

    const queryString = query.toString();
    return queryString ? `?${queryString}` : "";
}

function renderInventorySummary(items, pagination) {
    const total = document.getElementById("totalInventoryItems");
    const stockValue = document.getElementById("stockValue");
    const lowStock = document.getElementById("lowStockCount");
    const outOfStock = document.getElementById("outOfStockCount");
    const totalCount = pagination?.total_count ?? items.length;
    const visibleStockValue = items.reduce((sum, item) => {
        return sum + (Number(item.quantity || 0) * Number(item.product?.selling_price || 0));
    }, 0);

    if (total) total.textContent = String(totalCount);
    if (stockValue) stockValue.textContent = `NGN ${formatCurrency(visibleStockValue)}`;
    if (lowStock) lowStock.textContent = String(items.filter(item => item.is_low_stock).length);
    if (outOfStock) outOfStock.textContent = String(items.filter(item => item.is_out_of_stock).length);
}

function renderInventoryTable(items) {
    const tableBody = document.getElementById("inventoryTableBody");
    if (!tableBody) return;

    if (!items.length) {
        tableBody.innerHTML = "";
        showInventoryEmpty(true);
        return;
    }

    showInventoryEmpty(false);
    tableBody.innerHTML = items.map(item => {
        const product = item.product || {};
        const category = product.category || {};
        const unitPrice = Number(product.selling_price || 0);
        const stockValue = unitPrice * Number(item.quantity || 0);
        const statusClass = statusClassName(item.stock_status);

        return `
            <tr>
                <td data-label="Product"><strong>${escapeHtml(product.name || "Unknown product")}</strong></td>
                <td data-label="Category">${escapeHtml(category.name || "Uncategorised")}</td>
                <td data-label="SKU">${escapeHtml(item.sku || product.sku || "-")}</td>
                <td data-label="On hand">${formatNumber(item.quantity)}</td>
                <td data-label="Reorder">${formatNumber(item.reorder_level)}</td>
                <td data-label="Unit price">NGN ${formatCurrency(unitPrice)}</td>
                <td data-label="Stock value">NGN ${formatCurrency(stockValue)}</td>
                <td data-label="Status"><span class="stock-status ${statusClass}">${formatStatus(item.stock_status)}</span></td>
                <td data-label="Details"><button type="button" class="btn btn-secondary table-action" data-inventory-detail="${item.id}">View</button></td>
            </tr>
        `;
    }).join("");
}

function renderInventoryDetail(item) {
    const product = item.product || {};
    const category = product.category || {};
    return [
        detailMetric("Product", product.name || "-"),
        detailMetric("SKU", item.sku || product.sku || "-"),
        detailMetric("Category", category.name || "-"),
        detailMetric("Quantity", formatNumber(item.quantity)),
        detailMetric("Reorder level", formatNumber(item.reorder_level)),
        detailMetric("Stock status", formatStatus(item.stock_status)),
        detailMetric("Low stock", item.is_low_stock ? "Yes" : "No"),
        detailMetric("Out of stock", item.is_out_of_stock ? "Yes" : "No"),
        detailMetric("Unit price", `NGN ${formatCurrency(product.selling_price || 0)}`),
        detailMetric("Product active", product.is_active ? "Yes" : "No"),
        detailMetric("Created", formatDateTime(item.created_at)),
        detailMetric("Updated", formatDateTime(item.updated_at)),
    ].join("");
}

function renderMovementTable(movements) {
    const tableBody = document.getElementById("inventoryMovementTableBody");
    if (!tableBody) return;

    if (!movements.length) {
        tableBody.innerHTML = "";
        showMovementEmpty(true);
        return;
    }

    showMovementEmpty(false);
    tableBody.innerHTML = movements.map(movement => `
        <tr>
            <td data-label="Date">${formatDateTime(movement.created_at)}</td>
            <td data-label="Type">${escapeHtml(formatMovementType(movement.movement_type))}</td>
            <td data-label="Delta"><span class="stock-status ${movementClass(movement.quantity)}">${formatDelta(movement.quantity)}</span></td>
            <td data-label="Previous">${formatNumber(movement.previous_quantity)}</td>
            <td data-label="New">${formatNumber(movement.new_quantity)}</td>
            <td data-label="Reason">${escapeHtml(movement.reason || "-")}</td>
            <td data-label="Reference">${escapeHtml(movement.reference || "-")}</td>
            <td data-label="Created by">${escapeHtml(formatUser(movement.created_by))}</td>
        </tr>
    `).join("");
}

function renderPagination(elementId, pagination, onPageChange) {
    const container = document.getElementById(elementId);
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
        button.addEventListener("click", () => onPageChange(Number(button.dataset.page)));
    });
}

function showInventoryError(message) {
    const errorState = document.getElementById("inventoryErrorState");
    const errorMessage = document.getElementById("inventoryErrorMessage");
    if (!errorState) return;

    if (!message) {
        errorState.classList.add("inventory-state-hidden");
        return;
    }

    if (errorMessage) errorMessage.textContent = message;
    errorState.classList.remove("inventory-state-hidden");
}

function showInventoryEmpty(show) {
    document.getElementById("inventoryEmptyState")?.classList.toggle("empty-state-hidden", !show);
}

function showMovementEmpty(show) {
    document.getElementById("inventoryMovementEmptyState")?.classList.toggle("empty-state-hidden", !show);
}

function detailMetric(label, value) {
    return `<div class="detail-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value ?? "-"))}</strong></div>`;
}

function detailLoading() {
    return detailMetric("Status", "Loading detail...");
}

function loadingRow(message, colspan) {
    return `<tr><td colspan="${colspan}">${escapeHtml(message)}</td></tr>`;
}

function errorRow(message, colspan) {
    return `<tr><td colspan="${colspan}">${escapeHtml(message)}</td></tr>`;
}

function formatStatus(status) {
    if (status === "IN_STOCK") return "In stock";
    if (status === "LOW_STOCK") return "Low stock";
    if (status === "OUT_OF_STOCK") return "Out of stock";
    return "Unknown";
}

function statusClassName(status) {
    if (status === "LOW_STOCK") return "status-low-stock";
    if (status === "OUT_OF_STOCK") return "status-out-of-stock";
    return "status-in-stock";
}

function movementClass(quantity) {
    const value = Number(quantity || 0);
    if (value > 0) return "status-in-stock";
    if (value < 0) return "status-out-of-stock";
    return "status-low-stock";
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

function formatCurrency(value) {
    return Number(value || 0).toLocaleString("en-NG", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
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

function debounce(callback, delay) {
    let timerId;
    return (...args) => {
        window.clearTimeout(timerId);
        timerId = window.setTimeout(() => callback(...args), delay);
    };
}
