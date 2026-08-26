/**
 * MADAM HY - Customer Order Detail
 * Frontend-only order detail view
 */

/** MADAM HY - Customer Order Detail */

document.addEventListener('DOMContentLoaded', loadCustomerOrderDetail);

async function loadCustomerOrderDetail() {
    const orderId = Number(new URLSearchParams(window.location.search).get('id'));
    if (!orderId) {
        showDetailMessage('Order ID was not found.');
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
    document.getElementById('detailOrderRef')?.replaceChildren(document.createTextNode(`Order ${order.order_number}`));
    document.getElementById('detailOrderDate')?.replaceChildren(document.createTextNode(`Placed on ${formatDate(order.created_at)}`));
    document.getElementById('detailOrderStatus')?.replaceChildren(document.createTextNode(order.status));
    document.getElementById('detailReference')?.replaceChildren(document.createTextNode(order.order_number));
    document.getElementById('detailPlacedDate')?.replaceChildren(document.createTextNode(formatDate(order.created_at)));
    document.getElementById('detailOrderTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(order.total)}`));
    document.getElementById('detailPaymentStatus')?.replaceChildren(document.createTextNode(order.payment_status));
    document.getElementById('detailDeliveryAddress')?.replaceChildren(document.createTextNode(order.notes || 'Not provided'));
    document.getElementById('detailDeliveryMethod')?.replaceChildren(document.createTextNode(order.payment_method));

    const items = document.getElementById('detailOrderItems');
    if (items) {
        items.innerHTML = (order.items || []).map(item => `
            <div class="order-item-row">
                <div class="order-item-name">${escapeHtml(item.product_name_snapshot)}</div>
                <div class="order-item-qty">x${item.quantity}</div>
                <div class="order-item-price">₦${formatCurrency(item.line_total)}</div>
            </div>
        `).join('');
    }
    const timeline = document.getElementById('detailTimeline');
    if (timeline) {
        timeline.innerHTML = `<div class="timeline-item"><strong>Order placed</strong><span>Your order was received.</span><span>${formatDate(order.created_at)}</span></div>`;
    }
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

function formatCurrency(value) { return Number(value || 0).toLocaleString('en-NG'); }
function formatDate(value) { return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = value == null ? '' : String(value);
    return element.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    renderDetail();
});

function renderDetail() {
    document.getElementById('detailOrderRef')?.replaceChildren(document.createTextNode(`Order ${orderDetailData.id}`));
    document.getElementById('detailOrderDate')?.replaceChildren(document.createTextNode(`Placed on ${formatDate(orderDetailData.date)}`));
    document.getElementById('detailOrderStatus')?.replaceChildren(document.createTextNode(orderDetailData.status));
    const orderStatus = document.getElementById('detailOrderStatus');
    if (orderStatus) orderStatus.className = 'badge badge-primary';

    document.getElementById('detailReference')?.replaceChildren(document.createTextNode(orderDetailData.id));
    document.getElementById('detailPlacedDate')?.replaceChildren(document.createTextNode(formatDate(orderDetailData.date)));
    document.getElementById('detailOrderTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(orderDetailData.total)}`));
    document.getElementById('detailPaymentStatus')?.replaceChildren(document.createTextNode(orderDetailData.payment));
    document.getElementById('detailDeliveryAddress')?.replaceChildren(document.createTextNode(orderDetailData.deliveryAddress));
    document.getElementById('detailDeliveryMethod')?.replaceChildren(document.createTextNode(orderDetailData.deliveryMethod));

    const itemsList = document.getElementById('detailOrderItems');
    if (itemsList) {
        itemsList.innerHTML = orderDetailData.items.map(item => `
            <div class="order-item-row">
                <div class="order-item-name">${item.name}</div>
                <div class="order-item-qty">x${item.quantity}</div>
                <div class="order-item-price">₦${formatCurrency(item.price * item.quantity)}</div>
            </div>
        `).join('');
    }

    const timeline = document.getElementById('detailTimeline');
    if (timeline) {
        timeline.innerHTML = orderDetailData.timeline.map(item => `
            <div class="timeline-item">
                <strong>${item.title}</strong>
                <span>${item.text}</span>
                <span>${formatDate(item.date)}</span>
            </div>
        `).join('');
    }
}

function formatCurrency(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
