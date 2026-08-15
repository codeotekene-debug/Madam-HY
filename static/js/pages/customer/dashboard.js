/**
 * MADAM HY - Customer Dashboard
 * Demo data and customer account overview
 */

const customerData = {
    name: 'Aisha Bello',
    email: 'aisha@email.com',
    memberSince: '2025-06-15',
    totalOrders: 12,
    creditBalance: 15000,
    availableCredit: 45000,
    recentRequests: 2
};

const customerOrders = [
    {
        id: 'ORD-2026-0847',
        date: '2026-08-12',
        total: 28500,
        items: 3,
        status: 'Completed'
    },
    {
        id: 'ORD-2026-0846',
        date: '2026-08-08',
        total: 12300,
        items: 2,
        status: 'Completed'
    },
    {
        id: 'ORD-2026-0845',
        date: '2026-08-05',
        total: 45200,
        items: 5,
        status: 'Processing'
    }
];

const customerActivity = [
    { title: 'Order placed', text: 'Order ORD-2026-0847 was placed', date: '2026-08-12T10:30:00' },
    { title: 'Order delivered', text: 'Order ORD-2026-0846 was delivered', date: '2026-08-10T14:15:00' },
    { title: 'Payment received', text: 'Credit payment of ₦5,000 received', date: '2026-08-08T09:00:00' }
];

document.addEventListener('DOMContentLoaded', () => {
    renderDashboard();
});

function renderDashboard() {
    // Summary
    document.getElementById('totalOrders')?.replaceChildren(document.createTextNode(String(customerData.totalOrders)));
    document.getElementById('creditBalance')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(customerData.creditBalance)}`));
    document.getElementById('recentRequests')?.replaceChildren(document.createTextNode(String(customerData.recentRequests)));
    document.getElementById('availableCredit')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(customerData.availableCredit)}`));

    // Recent orders
    const ordersList = document.getElementById('recentOrdersList');
    const ordersEmpty = document.getElementById('recentOrdersEmpty');
    if (ordersList && customerOrders.length > 0) {
        ordersList.innerHTML = customerOrders.slice(0, 3).map(order => `
            <div class="order-item">
                <strong>${order.id}</strong>
                <span>${formatDate(order.date)} • ${order.items} items • ₦${formatCurrency(order.total)}</span>
            </div>
        `).join('');
        ordersEmpty?.classList.add('empty-state-hidden');
    } else {
        ordersEmpty?.classList.remove('empty-state-hidden');
    }

    // Recent activity
    const activityList = document.getElementById('recentActivityList');
    const activityEmpty = document.getElementById('recentActivityEmpty');
    if (activityList && customerActivity.length > 0) {
        activityList.innerHTML = customerActivity.slice(0, 3).map(item => `
            <div class="timeline-item">
                <strong>${item.title}</strong>
                <span>${item.text}</span>
                <span>${formatDate(item.date)}</span>
            </div>
        `).join('');
        activityEmpty?.classList.add('empty-state-hidden');
    } else {
        activityEmpty?.classList.remove('empty-state-hidden');
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
