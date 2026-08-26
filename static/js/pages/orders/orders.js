/** MADAM HY - Management Orders */

const managementOrderState = { page: 1, pageSize: 10, totalPages: 1, requestId: 0 };
const orderTransitions = {
    PENDING: ['CONFIRMED', 'CANCELLED'],
    CONFIRMED: ['PROCESSING', 'CANCELLED'],
    PROCESSING: ['READY', 'CANCELLED'],
    READY: ['COMPLETED', 'CANCELLED'],
};

document.addEventListener('DOMContentLoaded', () => {
    bindManagementOrderFilters();
    bindManagementOrderPagination();
    loadManagementOrders();
});

function bindManagementOrderFilters() {
    const search = document.getElementById('ordersSearch');
    const status = document.getElementById('ordersStatusFilter');
    const payment = document.getElementById('ordersPaymentFilter');
    const customer = document.getElementById('ordersCustomerFilter');
    const dateFrom = document.getElementById('ordersDateFrom');
    const dateTo = document.getElementById('ordersDateTo');
    const ordering = document.getElementById('ordersOrdering');
    const refresh = () => {
        managementOrderState.page = 1;
        loadManagementOrders();
    };
    let timer;
    search?.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(refresh, 300);
    });
    status?.addEventListener('change', refresh);
    payment?.addEventListener('change', refresh);
    customer?.addEventListener('change', refresh);
    dateFrom?.addEventListener('change', refresh);
    dateTo?.addEventListener('change', refresh);
    ordering?.addEventListener('change', refresh);
}

function bindManagementOrderPagination() {
    document.getElementById('ordersPrevious')?.addEventListener('click', () => {
        if (managementOrderState.page > 1) {
            managementOrderState.page -= 1;
            loadManagementOrders();
        }
    });
    document.getElementById('ordersNext')?.addEventListener('click', () => {
        if (managementOrderState.page < managementOrderState.totalPages) {
            managementOrderState.page += 1;
            loadManagementOrders();
        }
    });
}

async function loadManagementOrders() {
    const tableBody = document.getElementById('ordersTableBody');
    if (!tableBody) return;
    const params = new URLSearchParams({
        page: String(managementOrderState.page),
        page_size: String(managementOrderState.pageSize),
        search: document.getElementById('ordersSearch')?.value.trim() || '',
        status: getFilterValue('ordersStatusFilter'),
        payment_method: getFilterValue('ordersPaymentFilter'),
        customer: document.getElementById('ordersCustomerFilter')?.value.trim() || '',
        date_from: document.getElementById('ordersDateFrom')?.value || '',
        date_to: document.getElementById('ordersDateTo')?.value || '',
        ordering: document.getElementById('ordersOrdering')?.value || '-created_at',
    });
    ['search', 'status', 'payment_method', 'customer', 'date_from', 'date_to'].forEach(key => {
        if (!params.get(key)) params.delete(key);
    });
    setManagementOrderState('loading');
    const requestId = ++managementOrderState.requestId;
    const response = await apiRequest(`/orders/?${params.toString()}`);
    if (requestId !== managementOrderState.requestId) return;
    if (!response.success) {
        setManagementOrderState('error', response.message || 'Unable to load orders.', loadManagementOrders);
        return;
    }
    const orders = response.data?.orders || [];
    const pagination = response.data?.pagination || {};
    managementOrderState.totalPages = pagination.total_pages || 1;
    updateManagementPagination(pagination);
    renderManagementSummary(orders, pagination.total_count || orders.length);
    if (!orders.length) {
        tableBody.replaceChildren();
        setManagementOrderState('empty');
        return;
    }
    hideManagementOrderState();
    tableBody.innerHTML = orders.map(renderManagementOrder).join('');
    bindManagementRowActions();
}

function renderManagementOrder(order) {
    const customer = order.customer?.full_name || order.customer?.email || 'Guest';
    const status = String(order.status || '').toUpperCase();
    const actions = orderTransitions[status] || [];
    const actionMarkup = actions.length
        ? `<select class="form-select order-status-action" data-order-id="${order.id}" aria-label="Update order status">
            <option value="">Update status</option>
            ${actions.map(action => `<option value="${action}">${formatLabel(action)}</option>`).join('')}
        </select>`
        : '<span class="muted-text">No actions</span>';
    const convert = status === 'CONFIRMED' && canConvertOrders()
        ? `<button type="button" class="btn btn-secondary btn-sm order-convert-action" data-order-id="${order.id}">Convert to sale</button>`
        : '';
    return `
        <tr>
            <td data-label="Order #">${escapeHtml(order.order_number)}</td>
            <td data-label="Customer">${escapeHtml(customer)}</td>
            <td data-label="Date">${formatDate(order.created_at)}</td>
            <td data-label="Items">${order.item_count ?? 0}</td>
            <td data-label="Total">₦ ${formatCurrency(order.total)}</td>
            <td data-label="Order status"><span class="status-pill ${normalizeStatus(status)}">${formatLabel(status)}</span></td>
            <td data-label="Payment"><span class="payment-badge">${formatLabel(order.payment_method)}</span></td>
            <td data-label="Action" class="order-actions">
                <a href="/preview/orders/detail/?id=${encodeURIComponent(order.id)}" class="action-link">View</a>
                ${actionMarkup}
                ${convert}
            </td>
        </tr>
    `;
}

function bindManagementRowActions() {
    document.querySelectorAll('.order-status-action').forEach(select => select.addEventListener('change', async () => {
        const status = select.value;
        if (!status) return;
        if (status === 'CANCELLED' && !window.confirm('Cancel this order? This action cannot be reversed.')) {
            select.value = '';
            return;
        }
        await updateOrderStatus(select.dataset.orderId, status);
    }));
    document.querySelectorAll('.order-convert-action').forEach(button => button.addEventListener('click', async () => {
        if (!window.confirm('Convert this confirmed order to a completed sale? Inventory will be deducted.')) return;
        await convertOrder(button.dataset.orderId);
    }));
}

async function updateOrderStatus(orderId, status) {
    const response = await apiRequest(`/orders/${orderId}/status/`, { method: 'POST', body: { status } });
    if (!response.success) {
        window.alert(response.message || 'Unable to update order status.');
        return;
    }
    await loadManagementOrders();
}

async function convertOrder(orderId) {
    const response = await apiRequest(`/orders/${orderId}/convert-to-sale/`, { method: 'POST' });
    if (!response.success) {
        window.alert(response.message || 'Unable to convert order.');
        return;
    }
    await loadManagementOrders();
}

function renderManagementSummary(orders, totalCount) {
    document.getElementById('totalOrdersCount')?.replaceChildren(document.createTextNode(String(totalCount)));
    document.getElementById('pendingOrdersCount')?.replaceChildren(document.createTextNode(String(orders.filter(order => order.status === 'PENDING').length)));
    document.getElementById('completedOrdersCount')?.replaceChildren(document.createTextNode(String(orders.filter(order => order.status === 'COMPLETED').length)));
    document.getElementById('totalOrderValue')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(orders.reduce((sum, order) => sum + Number(order.total || 0), 0))}`));
}

function setManagementOrderState(state, message, retry) {
    const tableBody = document.getElementById('ordersTableBody');
    const empty = document.getElementById('ordersEmptyState');
    tableBody?.replaceChildren();
    if (!empty) return;
    empty.replaceChildren();
    const text = document.createElement('p');
    text.textContent = state === 'loading' ? 'Loading orders...' : message || 'No orders match your filters.';
    empty.append(text);
    if (state === 'error' && retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Retry';
        button.addEventListener('click', retry);
        empty.append(button);
    }
    empty.classList.remove('empty-state-hidden');
}

function hideManagementOrderState() { document.getElementById('ordersEmptyState')?.classList.add('empty-state-hidden'); }
function updateManagementPagination(pagination) {
    const page = pagination.page || managementOrderState.page;
    const totalPages = pagination.total_pages || 1;
    managementOrderState.page = page;
    document.getElementById('ordersPage')?.replaceChildren(document.createTextNode(`Page ${page} of ${totalPages}`));
    const previous = document.getElementById('ordersPrevious');
    const next = document.getElementById('ordersNext');
    if (previous) previous.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages;
}
function getFilterValue(id) {
    const value = document.getElementById(id)?.value || '';
    return value === 'all' ? '' : value;
}
function canConvertOrders() { return ['OWNER', 'MANAGER', 'CASHIER'].includes(getCurrentUserRole()); }
function normalizeStatus(value) { return String(value || '').toLowerCase().replaceAll('_', '-'); }
function formatLabel(value) { return String(value || '').toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatDate(value) { return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
