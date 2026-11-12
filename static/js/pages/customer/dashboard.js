/**
 * MADAM HY - Customer Dashboard
 * Dynamic customer metrics, recent orders, credit standing, and activity stream.
 */

let dashboardState = {
    customer: {},
    summary: {
        total_orders: 0,
        credit_balance: 0,
        recent_requests: 0,
        available_credit: 0
    },
    recent_orders: [],
    recent_activity: []
};

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

async function initDashboard() {
    const dataScript = document.getElementById('dashboardData');
    if (dataScript && dataScript.textContent.trim()) {
        try {
            const parsed = JSON.parse(dataScript.textContent);
            if (parsed && typeof parsed === 'object') {
                dashboardState = parsed;
                renderDashboard(dashboardState);
                return;
            }
        } catch (e) {
            console.warn('Could not parse embedded dashboardData:', e);
        }
    }

    // Fallback: fetch from API
    try {
        const response = await fetch('/customer/dashboard/?format=json', {
            headers: { 'Accept': 'application/json' }
        });
        if (response.ok) {
            const json = await response.json();
            if (json.success && json.data) {
                dashboardState = json.data;
                renderDashboard(dashboardState);
            }
        }
    } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
    }
}

function renderDashboard(data) {
    if (!data) return;

    const summary = data.summary || {};
    const customer = data.customer || {};

    // Hero Welcome
    const welcomeEl = document.getElementById('welcomeMessage');
    if (welcomeEl && customer.name) {
        welcomeEl.textContent = `Welcome back, ${customer.name} • Your shopping hub at MADAM HY`;
    }

    // Summary cards
    const totalOrdersEl = document.getElementById('totalOrders');
    if (totalOrdersEl && summary.total_orders !== undefined) {
        totalOrdersEl.textContent = String(summary.total_orders);
    }

    const creditBalanceEl = document.getElementById('creditBalance');
    if (creditBalanceEl && summary.credit_balance !== undefined) {
        creditBalanceEl.textContent = `₦ ${formatCurrency(summary.credit_balance)}`;
    }

    const recentRequestsEl = document.getElementById('recentRequests');
    if (recentRequestsEl && summary.recent_requests !== undefined) {
        recentRequestsEl.textContent = String(summary.recent_requests);
    }

    const availableCreditEl = document.getElementById('availableCredit');
    if (availableCreditEl && summary.available_credit !== undefined) {
        availableCreditEl.textContent = `₦ ${formatCurrency(summary.available_credit)}`;
    }

    // Recent orders
    const ordersList = document.getElementById('recentOrdersList');
    const ordersEmpty = document.getElementById('recentOrdersEmpty');
    const orders = data.recent_orders || [];

    if (ordersList) {
        if (orders.length > 0) {
            ordersList.innerHTML = orders.slice(0, 5).map(order => `
                <div class="order-item">
                    <strong>${order.order_number || order.id}</strong>
                    <span>${formatDate(order.date)} • ${order.items} items • ₦ ${formatCurrency(order.total)}</span>
                </div>
            `).join('');
            if (ordersEmpty) ordersEmpty.classList.add('empty-state-hidden');
        } else {
            ordersList.innerHTML = '';
            if (ordersEmpty) ordersEmpty.classList.remove('empty-state-hidden');
        }
    }

    // Recent activity
    const activityList = document.getElementById('recentActivityList');
    const activityEmpty = document.getElementById('recentActivityEmpty');
    const activities = data.recent_activity || [];

    if (activityList) {
        if (activities.length > 0) {
            activityList.innerHTML = activities.slice(0, 5).map(item => `
                <div class="timeline-item">
                    <strong>${item.title}</strong>
                    <span>${item.text}</span>
                    <span>${formatDate(item.date)}</span>
                </div>
            `).join('');
            if (activityEmpty) activityEmpty.classList.add('empty-state-hidden');
        } else {
            activityList.innerHTML = '';
            if (activityEmpty) activityEmpty.classList.remove('empty-state-hidden');
        }
    }
}

function formatCurrency(value) {
    if (value === null || value === undefined) return '0.00';
    const num = Number(value);
    if (isNaN(num)) return String(value);
    return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(value) {
    if (!value) return '';
    try {
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleDateString('en-GB', {
            day: '2-digit',
            month: 'short',
            year: 'numeric'
        });
    } catch (e) {
        return String(value);
    }
}
