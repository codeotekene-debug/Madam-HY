const expenseReportData = [
    { category: 'Rent', amount: 1800000, vendor: 'Landmark Properties', description: 'Shop rent and maintenance', date: '2026-08-14' },
    { category: 'Utilities', amount: 650000, vendor: 'Power Distribution', description: 'Electricity and water', date: '2026-08-12' },
    { category: 'Supplies', amount: 540000, vendor: 'ABC Supplies', description: 'Packaging and stationery', date: '2026-08-10' },
    { category: 'Maintenance', amount: 420000, vendor: 'Cool Tech', description: 'AC repairs and service', date: '2026-08-08' },
    { category: 'Transport', amount: 310000, vendor: 'Shell Station', description: 'Vehicle fuel and logistics', date: '2026-08-06' },
    { category: 'Salaries', amount: 1500000, vendor: 'Internal', description: 'Payroll disbursement', date: '2026-08-02' }
];

document.addEventListener('DOMContentLoaded', () => {
    renderExpenseSummary();
    renderTrendChart();
    renderCategoryList();
    renderExpenseTable();
});

function renderExpenseSummary() {
    const total = expenseReportData.reduce((sum, item) => sum + item.amount, 0);
    const average = total / expenseReportData.length;
    const top = expenseReportData.reduce((winner, item) => item.amount > winner.amount ? item : winner, expenseReportData[0]);

    document.getElementById('expenseTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));
    document.getElementById('expenseAverage')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(average)}`));
    document.getElementById('expenseTopCategory')?.replaceChildren(document.createTextNode(top.category));
    document.getElementById('expenseGrowth')?.replaceChildren(document.createTextNode('+9.5%'));
}

function renderTrendChart() {
    const chart = document.getElementById('expenseTrendChart');
    if (!chart) return;

    const values = [58, 61, 66, 72, 69, 80];
    chart.innerHTML = values.map((value, index) => `
        <div class="bar-segment" style="--value: ${value}%">
            <span>${['Jan','Feb','Mar','Apr','May','Jun'][index]}</span>
        </div>
    `).join('');
}

function renderCategoryList() {
    const container = document.getElementById('expenseCategoryList');
    if (!container) return;

    const total = expenseReportData.reduce((sum, item) => sum + item.amount, 0);
    container.innerHTML = expenseReportData.map(item => `
        <div class="category-item">
            <strong>${item.category}</strong>
            <span>${((item.amount / total) * 100).toFixed(1)}% · ₦ ${formatCurrency(item.amount)}</span>
        </div>
    `).join('');
}

function renderExpenseTable() {
    const tableBody = document.getElementById('expenseTableBody');
    const emptyState = document.getElementById('expenseEmptyState');

    if (!tableBody) return;

    if (!expenseReportData.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = expenseReportData.map(item => `
        <tr>
            <td>${item.category}</td>
            <td>${item.description}</td>
            <td>${item.vendor}</td>
            <td>${formatDate(item.date)}</td>
            <td>₦ ${formatCurrency(item.amount)}</td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
