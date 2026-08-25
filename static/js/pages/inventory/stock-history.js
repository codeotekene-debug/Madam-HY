/**
 * MADAM HY - Stock history API integration.
 * Read-only movement history backed by the Inventory Reporting API.
 */

const stockHistoryState = {
    inventory: [],
    selectedInventoryId: null,
    dateFrom: "",
    dateTo: "",
    page: 1,
    pageSize: 10,
};

document.addEventListener("DOMContentLoaded", () => {
    setupStockHistoryControls();
    loadInventoryOptions();
});

function setupStockHistoryControls() {
    document.getElementById("stockHistoryRetryButton")?.addEventListener("click", () => loadStockHistory());
    document.getElementById("stockHistoryErrorRetryButton")?.addEventListener("click", () => loadStockHistory());

    const select = document.getElementById("stockHistoryInventorySelect");
    const dateFrom = document.getElementById("stockHistoryDateFrom");
    const dateTo = document.getElementById("stockHistoryDateTo");
    const filterBtn = document.getElementById("stockHistoryFilterButton");
    const resetBtn = document.getElementById("stockHistoryResetButton");

    select?.addEventListener("change", event => {
        const val = event.target.value;
        stockHistoryState.selectedInventoryId = val ? Number(val) : null;
        stockHistoryState.page = 1;
        loadStockHistory();
    });

    filterBtn?.addEventListener("click", () => {
        stockHistoryState.dateFrom = dateFrom?.value || "";
        stockHistoryState.dateTo = dateTo?.value || "";
        stockHistoryState.page = 1;
        loadStockHistory();
    });

    resetBtn?.addEventListener("click", () => {
        if (dateFrom) dateFrom.value = "";
        if (dateTo) dateTo.value = "";
        if (select) select.value = "";
        stockHistoryState.dateFrom = "";
        stockHistoryState.dateTo = "";
        stockHistoryState.selectedInventoryId = null;
        stockHistoryState.page = 1;
        loadStockHistory();
    });
}

async function loadInventoryOptions() {
    const select = document.getElementById("stockHistoryInventorySelect");
    if (!select) return;

    select.innerHTML = `<option value="">Loading inventory...</option>`;

    const response = await apiRequest("/inventory/?page_size=100&sort_by=product_name");
    if (!response.success) {
        select.innerHTML = `<option value="">All inventory items</option>`;
        loadStockHistory();
        return;
    }

    stockHistoryState.inventory = response.data?.inventory || [];
    renderInventorySelect();
    loadStockHistory();
}

async function loadStockHistory() {
    const tableBody = document.getElementById("stockHistoryTableBody");
    if (!tableBody) return;

    showStockHistoryError("");
    showStockHistoryEmpty(false);
    tableBody.innerHTML = loadingRow("Loading movement history...", 8);

    const queryParams = new URLSearchParams({
        page: String(stockHistoryState.page),
        page_size: String(stockHistoryState.pageSize),
    });

    if (stockHistoryState.dateFrom) queryParams.set("date_from", stockHistoryState.dateFrom);
    if (stockHistoryState.dateTo) queryParams.set("date_to", stockHistoryState.dateTo);

    // If an item is selected, pass its product_id
    if (stockHistoryState.selectedInventoryId) {
        const selectedItem = stockHistoryState.inventory.find(i => i.id === stockHistoryState.selectedInventoryId);
        if (selectedItem?.product?.id) {
            queryParams.set("product_id", String(selectedItem.product.id));
        }
    }

    const reportUrl = `/inventory/reports/movements/?${queryParams.toString()}`;
    const response = await apiRequest(reportUrl);

    if (response.success && response.data) {
        const summary = response.data.summary || {
            total_movements: response.data.pagination?.total_count ?? 0,
            stock_in_quantity: response.data.stock_in_quantity ?? 0,
            stock_out_quantity: response.data.stock_out_quantity ?? 0,
            net_movement: response.data.net_movement ?? 0,
        };
        const movements = response.data.movements || [];
        const pagination = response.data.pagination || null;

        renderStockHistorySummary(summary);
        renderStockHistory(movements);
        renderPagination(pagination);
        return;
    }

    // Fallback if reports endpoint fails
    if (stockHistoryState.selectedInventoryId) {
        const fallbackUrl = `/inventory/${stockHistoryState.selectedInventoryId}/movements/?${queryParams.toString()}`;
        const fallbackResponse = await apiRequest(fallbackUrl);
        if (fallbackResponse.success) {
            const movements = fallbackResponse.data?.movements || [];
            const pagination = fallbackResponse.data?.pagination || null;
            const inQty = movements.filter(m => m.quantity > 0).reduce((s, m) => s + m.quantity, 0);
            const outQty = movements.filter(m => m.quantity < 0).reduce((s, m) => s + Math.abs(m.quantity), 0);
            renderStockHistorySummary({
                total_movements: pagination?.total_count ?? movements.length,
                stock_in_quantity: inQty,
                stock_out_quantity: outQty,
                net_movement: inQty - outQty,
            });
            renderStockHistory(movements);
            renderPagination(pagination);
            return;
        }
    }

    tableBody.innerHTML = "";
    renderStockHistorySummary({
        total_movements: 0,
        stock_in_quantity: 0,
        stock_out_quantity: 0,
        net_movement: 0,
    });
    renderPagination(null);
    showStockHistoryError(response.message || "Stock history could not load.");
}

function renderInventorySelect() {
    const select = document.getElementById("stockHistoryInventorySelect");
    if (!select) return;

    const options = [
        '<option value="">All inventory items</option>',
        ...stockHistoryState.inventory.map(item => {
            const product = item.product || {};
            return `<option value="${item.id}">${escapeHtml(product.name || "Unknown product")} (${escapeHtml(item.sku || product.sku || "-")})</option>`;
        }),
    ];

    select.innerHTML = options.join("");
    if (stockHistoryState.selectedInventoryId) {
        select.value = String(stockHistoryState.selectedInventoryId);
    }
}

function renderStockHistorySummary(summary) {
    const totalEl = document.getElementById("stockHistoryTotalMovements");
    const inEl = document.getElementById("stockHistoryStockIn");
    const outEl = document.getElementById("stockHistoryStockOut");
    const netEl = document.getElementById("stockHistoryNetMovement");

    if (totalEl) totalEl.textContent = formatNumber(summary.total_movements ?? 0);
    if (inEl) inEl.textContent = formatNumber(summary.stock_in_quantity ?? 0);
    if (outEl) outEl.textContent = formatNumber(summary.stock_out_quantity ?? 0);
    if (netEl) {
        const net = Number(summary.net_movement ?? 0);
        netEl.textContent = net > 0 ? `+${formatNumber(net)}` : formatNumber(net);
    }
}

function renderStockHistory(movements) {
    const tableBody = document.getElementById("stockHistoryTableBody");
    if (!tableBody) return;

    if (!movements.length) {
        tableBody.innerHTML = "";
        showStockHistoryEmpty(true);
        return;
    }

    showStockHistoryEmpty(false);
    tableBody.innerHTML = movements.map(item => {
        const movementClass = movementPillClass(item.quantity);
        const productName = item.product?.name || "Unknown product";
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
