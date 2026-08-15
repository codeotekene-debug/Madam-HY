const growthData = [
    { label: 'Jan', sales: 12, revenue: 14, customers: 8, orders: 10, profit: 9 },
    { label: 'Feb', sales: 16, revenue: 17, customers: 12, orders: 14, profit: 13 },
    { label: 'Mar', sales: 19, revenue: 21, customers: 16, orders: 18, profit: 17 },
    { label: 'Apr', sales: 24, revenue: 26, customers: 20, orders: 22, profit: 21 },
    { label: 'May', sales: 28, revenue: 30, customers: 24, orders: 27, profit: 25 },
    { label: 'Jun', sales: 34, revenue: 36, customers: 28, orders: 30, profit: 32 }
];

document.addEventListener('DOMContentLoaded', () => {
    renderGrowthSummary();
    renderGrowthChart();
    renderDrivers();
    renderNotes();
});

function renderGrowthSummary() {
    document.getElementById('growthSales')?.replaceChildren(document.createTextNode('+24.5%'));
    document.getElementById('growthRevenue')?.replaceChildren(document.createTextNode('+28.1%'));
    document.getElementById('growthCustomers')?.replaceChildren(document.createTextNode('+18.7%'));
    document.getElementById('growthOrders')?.replaceChildren(document.createTextNode('+21.4%'));
    document.getElementById('growthProfit')?.replaceChildren(document.createTextNode('+26.6%'));
    document.getElementById('growthAverage')?.replaceChildren(document.createTextNode('+23.9%'));
}

function renderGrowthChart() {
    const chart = document.getElementById('growthChart');
    if (!chart) return;

    chart.innerHTML = growthData.map(item => `
        <div class="growth-point">
            <div class="growth-bar" style="height:${item.sales}%"></div>
            <span>${item.label}</span>
        </div>
    `).join('');
}

function renderDrivers() {
    const drivers = document.getElementById('growthDrivers');
    if (!drivers) return;

    const items = [
        { name: 'Sales volume', value: '+24.5%' },
        { name: 'Customer acquisition', value: '+18.7%' },
        { name: 'Average basket size', value: '+12.4%' },
        { name: 'Product mix', value: '+9.3%' }
    ];

    drivers.innerHTML = items.map(item => `
        <div class="growth-item">
            <strong>${item.name}</strong>
            <span>${item.value}</span>
        </div>
    `).join('');
}

function renderNotes() {
    const notes = document.getElementById('growthNotes');
    if (!notes) return;

    const items = [
        { title: 'Demand strength', text: 'High demand in household and beauty categories.' },
        { title: 'Retention', text: 'Returning customer rate reached 39% this cycle.' },
        { title: 'Operations', text: 'Delivery and staffing costs remained stable.' }
    ];

    notes.innerHTML = items.map(item => `
        <div class="note-item">
            <strong>${item.title}</strong>
            <span>${item.text}</span>
        </div>
    `).join('');
}
