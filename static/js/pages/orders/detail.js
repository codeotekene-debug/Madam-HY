/** MADAM HY - Management Order Detail */

const managementOrderStatuses = ['PENDING', 'CONFIRMED', 'PROCESSING', 'READY', 'COMPLETED'];
const managementTransitions = {
    PENDING: ['CONFIRMED', 'CANCELLED'],
    CONFIRMED: ['PROCESSING', 'CANCELLED'],
    PROCESSING: ['READY', 'CANCELLED'],
    READY: ['COMPLETED', 'CANCELLED'],
};

document.addEventListener('DOMContentLoaded', loadManagementOrderDetail);

async function loadManagementOrderDetail() {
    const orderId = Number(new URLSearchParams(window.location.search).get('id'));
    if (!orderId) {
        showDetailState('Order ID was not found.', true);
        return;
    }
    showDetailState('Loading order details...');
    const response = await apiRequest(`/orders/${orderId}/`);
    if (!response.success || !response.data?.order) {
        showDetailState(response.message || 'Unable to load order details.', true, loadManagementOrderDetail);
        return;
    }
    renderManagementOrderDetail(response.data.order);
}

function renderManagementOrderDetail(order) {
    const status = String(order.status || '').toUpperCase();
    document.getElementById('detailOrderNumber')?.replaceChildren(document.createTextNode(`Order #${order.order_number}`));
    document.getElementById('detailOrderDate')?.replaceChildren(document.createTextNode(formatDate(order.created_at)));
    setStatus(document.getElementById('detailOrderStatus'), status);
    document.getElementById('detailCustomer')?.replaceChildren(document.createTextNode(order.customer?.full_name || order.customer?.email || 'Guest'));
    document.getElementById('detailPhone')?.replaceChildren(document.createTextNode(order.customer_phone || 'Not provided'));
    document.getElementById('detailDateField')?.replaceChildren(document.createTextNode(formatDate(order.created_at)));
    document.getElementById('detailAddress')?.replaceChildren(document.createTextNode(order.delivery_address || 'Not provided'));
    document.getElementById('detailPaymentMethod')?.replaceChildren(document.createTextNode(formatLabel(order.payment_method)));
    document.getElementById('detailPaymentStatus')?.replaceChildren(document.createTextNode(formatLabel(order.payment_status)));
    document.getElementById('detailStatusField')?.replaceChildren(document.createTextNode(formatLabel(status)));
    document.getElementById('detailAssignedStaff')?.replaceChildren(document.createTextNode(order.created_by?.full_name || order.created_by?.email || 'Not assigned'));
    document.getElementById('detailSubtotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.subtotal)}`));
    document.getElementById('detailDiscount')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.discount)}`));
    document.getElementById('detailTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.total)}`));

    const items = document.getElementById('detailItemsBody');
    if (items) {
        items.innerHTML = (order.items || []).map(item => `
            <tr>
                <td>${escapeHtml(item.product_name_snapshot)}</td>
                <td>${item.quantity}</td>
                <td>₦ ${formatCurrency(item.unit_price)}</td>
                <td>₦ ${formatCurrency(item.line_total)}</td>
            </tr>
        `).join('');
    }
    renderDetailActions(order, status);
}

function renderDetailActions(order, status) {
    const container = document.getElementById('orderDetailActions');
    if (!container) return;
    const actions = managementTransitions[status] || [];
    container.replaceChildren();
    actions.forEach(nextStatus => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = nextStatus === 'CANCELLED' ? 'btn btn-secondary btn-sm' : 'btn btn-primary btn-sm';
        button.textContent = `Mark ${formatLabel(nextStatus)}`;
        button.addEventListener('click', async () => {
            if (nextStatus === 'CANCELLED' && !window.confirm('Cancel this order? This action cannot be reversed.')) return;
            await updateStatus(order.id, nextStatus);
        });
        container.append(button);
    });
    if (status === 'CONFIRMED' && canConvertOrders()) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Convert to sale';
        button.addEventListener('click', async () => {
            if (!window.confirm('Convert this confirmed order to a completed sale? Inventory will be deducted.')) return;
            await convertOrder(order.id);
        });
        container.append(button);
    }
}

async function updateStatus(orderId, status) {
    const response = await apiRequest(`/orders/${orderId}/status/`, { method: 'POST', body: { status } });
    if (!response.success) {
        window.alert(response.message || 'Unable to update order status.');
        return;
    }
    await loadManagementOrderDetail();
}

async function convertOrder(orderId) {
    const response = await apiRequest(`/orders/${orderId}/convert-to-sale/`, { method: 'POST' });
    if (!response.success) {
        window.alert(response.message || 'Unable to convert order.');
        return;
    }
    await loadManagementOrderDetail();
}

function showDetailState(message, isError = false, retry) {
    const target = document.getElementById('detailItemsBody');
    if (!target) return;
    target.replaceChildren();
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.textContent = message;
    row.append(cell);
    target.append(row);
    if (isError && retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Retry';
        button.addEventListener('click', retry);
        cell.append(document.createTextNode(' '), button);
    }
}

function setStatus(element, status) {
    if (!element) return;
    element.textContent = formatLabel(status);
    element.className = `status-pill ${normalizeStatus(status)}`;
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
