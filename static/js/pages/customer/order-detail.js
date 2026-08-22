/**
 * MADAM HY - Customer Order Detail
 * Frontend-only order detail view
 */

const orderDetailData = {
    id: 'ORD-2026-0847',
    date: '2026-08-12T10:30:00',
    items: [
        { name: "Green Ankara Fabric Premium", quantity: 2, price: 12500 },
        { name: "Radiant Glow Serum", quantity: 1, price: 9500 }
    ],
    subtotal: 34500,
    tax: 2588,
    total: 37088,
    status: 'Completed',
    payment: 'Card',
    deliveryAddress: '123 Main Street, Lagos',
    deliveryMethod: 'Delivery',
    timeline: [
        { title: 'Order placed', text: 'Your order was successfully placed', date: '2026-08-12T10:30:00' },
        { title: 'Order confirmed', text: 'Order has been confirmed and is being processed', date: '2026-08-12T11:15:00' },
        { title: 'Order shipped', text: 'Your order has been shipped', date: '2026-08-13T08:00:00' },
        { title: 'Order delivered', text: 'Your order has been delivered', date: '2026-08-14T14:30:00' }
    ]
};

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
