/** MADAM HY - Customer Order Detail */

const customerOrderStatuses = ['PENDING', 'CONFIRMED', 'PROCESSING', 'READY', 'COMPLETED'];

document.addEventListener('DOMContentLoaded', loadCustomerOrderDetail);

async function loadCustomerOrderDetail() {
    const orderId = Number(new URLSearchParams(window.location.search).get('id'));
    if (!orderId) {
        showDetailMessage('Order ID was not found.', true);
        return;
    }

    showDetailMessage('Loading order details...');
    const response = await apiRequest(`/orders/${orderId}/`);
    if (!response.success || !response.data?.order) {
        showDetailMessage(response.message || 'Unable to load order details.', true, loadCustomerOrderDetail);
        return;
    }
    renderDetail(response.data.order);
}

function renderDetail(order) {
    const status = String(order.status || '').toUpperCase();
    document.getElementById('detailOrderRef')?.replaceChildren(document.createTextNode(`Order ${order.order_number}`));
    document.getElementById('detailOrderDate')?.replaceChildren(document.createTextNode(`Placed on ${formatDate(order.created_at)}`));
    setStatusElement(document.getElementById('detailOrderStatus'), status);
    document.getElementById('detailReference')?.replaceChildren(document.createTextNode(order.order_number));
    document.getElementById('detailPlacedDate')?.replaceChildren(document.createTextNode(formatDate(order.created_at)));
    document.getElementById('detailOrderTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.total)}`));
    document.getElementById('detailPaymentMethod')?.replaceChildren(document.createTextNode(formatLabel(order.payment_method)));
    document.getElementById('detailPaymentStatus')?.replaceChildren(document.createTextNode(formatLabel(order.payment_status)));
    document.getElementById('detailCustomer')?.replaceChildren(document.createTextNode(order.customer?.full_name || order.customer?.email || 'Customer'));
    document.getElementById('detailOrderNotes')?.replaceChildren(document.createTextNode(order.notes || 'No notes provided'));

    const items = document.getElementById('detailOrderItems');
    if (items) {
        if (!order.items?.length) {
            items.replaceChildren(document.createTextNode('No items were recorded for this order.'));
        } else {
            items.innerHTML = order.items.map(item => `
                <div class="order-item-row">
                    <div class="order-item-name">${escapeHtml(item.product_name_snapshot)}</div>
                    <div class="order-item-qty">x${item.quantity}</div>
                    <div class="order-item-price">₦${formatCurrency(item.line_total)}</div>
                </div>
            `).join('');
        }
    }

    renderTimeline(status, order.created_at);
}

function renderTimeline(currentStatus, createdAt) {
    const timeline = document.getElementById('detailTimeline');
    if (!timeline) return;
    if (currentStatus === 'CANCELLED') {
        timeline.innerHTML = `
            <div class="timeline-item cancelled current">
                <strong>Cancelled</strong>
                <span>This order is cancelled.</span>
                <span>${formatDate(createdAt)}</span>
            </div>
        `;
        return;
    }

    const currentIndex = customerOrderStatuses.indexOf(currentStatus);
    timeline.innerHTML = customerOrderStatuses.map((status, index) => {
        const state = index < currentIndex ? 'completed' : index === currentIndex ? 'current' : 'upcoming';
        const description = state === 'completed' ? 'Completed' : state === 'current' ? 'Current status' : 'Upcoming';
        return `
            <div class="timeline-item ${state}">
                <strong>${formatLabel(status)}</strong>
                <span>${description}</span>
                <span>${state === 'current' || status === 'PENDING' ? formatDate(createdAt) : ''}</span>
            </div>
        `;
    }).join('');
}

function setStatusElement(element, status) {
    if (!element) return;
    element.textContent = formatLabel(status);
    element.className = `badge badge-primary status-${normalizeStatus(status)}`;
}

function showDetailMessage(message, isError = false, retry) {
    const target = document.getElementById('detailOrderItems');
    if (!target) return;
    target.replaceChildren();
    const text = document.createElement('p');
    text.textContent = message;
    target.append(text);
    if (isError && retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Retry';
        button.addEventListener('click', retry);
        target.append(button);
    }
}

function normalizeStatus(value) { return String(value || '').toLowerCase().replaceAll('_', '-'); }
function formatLabel(value) { return String(value || '').toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatDate(value) { return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
