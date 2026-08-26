/**
 * MADAM HY - Customer Orders
 * Frontend-only customer order list
 */

/** MADAM HY - Customer Orders */

const customerOrderState = { page: 1, pageSize: 10, requestId: 0 };

document.addEventListener('DOMContentLoaded', () => {
    bindOrderFilters();
    bindOrderPagination();
    loadCustomerOrders();
});

function bindOrderFilters() {
    const search = document.getElementById('customerOrdersSearch');
    const status = document.getElementById('customerOrdersStatusFilter');
    let timer;
    const refresh = () => {
        customerOrderState.page = 1;
        loadCustomerOrders();
    };
    search?.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(refresh, 300);
    });
    status?.addEventListener('change', refresh);
}

function bindOrderPagination() {
    document.getElementById('customerOrdersPrevious')?.addEventListener('click', () => {
        if (customerOrderState.page > 1) {
            customerOrderState.page -= 1;
            loadCustomerOrders();
        }
    });
    document.getElementById('customerOrdersNext')?.addEventListener('click', () => {
        if (customerOrderState.page < customerOrderState.totalPages) {
            customerOrderState.page += 1;
            loadCustomerOrders();
        }
    });
}

async function loadCustomerOrders() {
    const tableBody = document.getElementById('customerOrdersTableBody');
    if (!tableBody) return;
    const params = new URLSearchParams({
        page: String(customerOrderState.page),
        page_size: String(customerOrderState.pageSize),
        search: document.getElementById('customerOrdersSearch')?.value.trim() || '',
        status: getFilterValue('customerOrdersStatusFilter'),
    });
    if (!params.get('search')) params.delete('search');
    if (!params.get('status')) params.delete('status');

    const requestId = ++customerOrderState.requestId;
    setOrderState('loading');
    const response = await apiRequest(`/orders/?${params.toString()}`);
    if (requestId !== customerOrderState.requestId) return;
    if (!response.success) {
        setOrderState('error', response.message || 'Unable to load your orders.', loadCustomerOrders);
        return;
    }

    const orders = response.data?.orders || [];
    const pagination = response.data?.pagination || {};
    customerOrderState.totalPages = pagination.total_pages || 1;
    updateOrderPagination(pagination);
    renderOrderSummary(orders, pagination.total_count || orders.length);
    if (!orders.length) {
        tableBody.replaceChildren();
        setOrderState('empty');
        return;
    }
    hideOrderState();
    tableBody.innerHTML = orders.map(order => `
        <tr>
            <td data-label="Order #"><strong>${escapeHtml(order.order_number)}</strong></td>
            <td data-label="Date">${formatDate(order.created_at)}</td>
            <td data-label="Items">${order.item_count ?? 0}</td>
            <td data-label="Total">₦ ${formatCurrency(order.total)}</td>
            <td data-label="Status"><span class="order-status ${normalizeStatus(order.status)}">${escapeHtml(order.status)}</span></td>
            <td data-label="Action"><a href="/preview/customer/order-detail/?id=${encodeURIComponent(order.id)}" class="order-action-link">View</a></td>
        </tr>
    `).join('');
}

function renderOrderSummary(orders, totalCount) {
    document.getElementById('customerTotalOrders')?.replaceChildren(document.createTextNode(String(totalCount)));
    document.getElementById('customerPendingOrders')?.replaceChildren(document.createTextNode(String(orders.filter(order => ['PENDING', 'PROCESSING'].includes(order.status)).length)));
    document.getElementById('customerCompletedOrders')?.replaceChildren(document.createTextNode(String(orders.filter(order => order.status === 'COMPLETED').length)));
    document.getElementById('customerTotalSpent')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(orders.reduce((sum, order) => sum + Number(order.total || 0), 0))}`));
}

function setOrderState(state, message, retry) {
    const tableBody = document.getElementById('customerOrdersTableBody');
    const empty = document.getElementById('customerOrdersEmpty');
    tableBody?.replaceChildren();
    if (!empty) return;
    empty.replaceChildren();
    const text = document.createElement('p');
    text.textContent = state === 'loading' ? 'Loading your orders...' : message || 'No orders yet.';
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

function hideOrderState() {
    document.getElementById('customerOrdersEmpty')?.classList.add('empty-state-hidden');
}

function updateOrderPagination(pagination) {
    const page = pagination.page || customerOrderState.page;
    const totalPages = pagination.total_pages || 1;
    customerOrderState.page = page;
    document.getElementById('customerOrdersPage')?.replaceChildren(document.createTextNode(`Page ${page} of ${totalPages}`));
    const previous = document.getElementById('customerOrdersPrevious');
    const next = document.getElementById('customerOrdersNext');
    if (previous) previous.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages;
}

function getFilterValue(id) {
    const value = document.getElementById(id)?.value || '';
    return value === 'all' ? '' : value;
}

function normalizeStatus(value) {
    return String(value || '').toLowerCase().replaceAll('_', '-');
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString('en-NG');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
