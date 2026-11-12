/**
 * MADAM HY - Customer Order Detail Controller
 */

const customerOrderStatuses = ['PENDING', 'CONFIRMED', 'PROCESSING', 'READY', 'COMPLETED'];

document.addEventListener('DOMContentLoaded', loadCustomerOrderDetail);

function getOrderIdFromUrl() {
    const searchId = new URLSearchParams(window.location.search).get('id');
    if (searchId && !isNaN(Number(searchId))) return Number(searchId);

    const match = window.location.pathname.match(/\/orders\/(\d+)\/?/);
    if (match && match[1]) return Number(match[1]);

    const altMatch = window.location.pathname.match(/\/order-success\/(\d+)\/?/);
    if (altMatch && altMatch[1]) return Number(altMatch[1]);

    return null;
}

async function loadCustomerOrderDetail() {
    const orderId = getOrderIdFromUrl();
    if (!orderId) {
        // May already be server-rendered
        return;
    }

    const response = await apiRequest(`/orders/${orderId}/`);
    if (!response.success || !response.data?.order) {
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
    document.getElementById('detailHeroTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.total)}`));
    document.getElementById('detailPaymentMethod')?.replaceChildren(document.createTextNode(formatLabel(order.payment_method)));
    document.getElementById('detailPaymentStatus')?.replaceChildren(document.createTextNode(formatLabel(order.payment_status)));
    document.getElementById('detailPaymentStatusTop')?.replaceChildren(document.createTextNode(formatLabel(order.payment_status)));
    document.getElementById('detailCustomer')?.replaceChildren(document.createTextNode(order.customer?.full_name || order.customer?.username || order.customer?.email || 'Customer'));
    document.getElementById('detailCustomerPhone')?.replaceChildren(document.createTextNode(order.customer_phone || 'Provided at checkout'));
    document.getElementById('detailDeliveryAddress')?.replaceChildren(document.createTextNode(order.delivery_address || 'In-Store Counter Pickup'));
    document.getElementById('detailOrderNotes')?.replaceChildren(document.createTextNode(order.notes || 'No notes provided'));

    const items = document.getElementById('detailOrderItems');
    if (items && order.items?.length) {
        items.innerHTML = order.items.map(item => `
            <div class="order-item-row" style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px dashed #e2e8f0;">
                <div>
                    <strong style="font-size: 14px; color: #0f172a;">${escapeHtml(item.product_name_snapshot || item.product_name)}</strong>
                    <span style="font-size: 12.5px; color: #64748b; margin-left: 8px;">× ${item.quantity}</span>
                </div>
                <strong style="font-size: 14px; color: #0f172a;">₦ ${formatCurrency(item.line_total || item.total_price)}</strong>
            </div>
        `).join('');
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
                <span>This order was cancelled.</span>
                <span>${formatDate(createdAt)}</span>
            </div>
        `;
        return;
    }

    const currentIndex = customerOrderStatuses.indexOf(currentStatus);
    timeline.innerHTML = customerOrderStatuses.map((status, index) => {
        const state = index < currentIndex ? 'completed' : index === currentIndex ? 'current' : 'upcoming';
        const description = state === 'completed' ? 'Completed' : state === 'current' ? 'Current Status' : 'Upcoming';
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

function normalizeStatus(status) {
    return String(status || '').toLowerCase().replaceAll('_', '-');
}

function formatLabel(value) {
    if (!value) return '-';
    return String(value).replaceAll('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatDate(value) {
    if (!value) return '-';
    return new Date(value).toLocaleDateString('en-NG', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}
