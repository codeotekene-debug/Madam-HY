const profitReportData = [
    { label: 'Revenue', current: 12650000, previous: 10930000 },
    { label: 'Cost of sales', current: 4860000, previous: 4505000 },
    { label: 'Gross profit', current: 7790000, previous: 6425000 },
    { label: 'Operating expenses', current: 1850000, previous: 1710000 },
    { label: 'Net profit', current: 5940000, previous: 4715000 }
];

document.addEventListener('DOMContentLoaded', () => {
    renderProfitSummary();
    renderTrendChart();
    renderTable();
});

function renderProfitSummary() {
    const revenue = profitReportData[0].current;
    const cost = profitReportData[1].current;
    const gross = profitReportData[2].current;
    const expenses = profitReportData[3].current;
    const net = profitReportData[4].current;
    const margin = (net / revenue) * 100;

    document.getElementById('profitRevenue')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(revenue)}`));
    document.getElementById('profitCost')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(cost)}`));
    document.getElementById('profitGross')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(gross)}`));
    document.getElementById('profitExpenses')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(expenses)}`));
    document.getElementById('profitNet')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(net)}`));
    document.getElementById('profitMargin')?.replaceChildren(document.createTextNode(`${margin.toFixed(1)}%`));
}

function renderTrendChart() {
    const chart = document.getElementById('profitTrendChart');
    if (!chart) return;

    const values = [42, 52, 60, 72, 78, 88];
    chart.innerHTML = values.map((value, index) => `
        <div class="trend-item">
            <div class="trend-bar" style="height:${value}%"></div>
            <span>${['Jan','Feb','Mar','Apr','May','Jun'][index]}</span>
        </div>
    `).join('');
}

function renderTable() {
    const tableBody = document.getElementById('profitTableBody');
    if (!tableBody) return;

    tableBody.innerHTML = profitReportData.map(item => {
        const diff = ((item.current - item.previous) / item.previous) * 100;
        return `
            <tr>
                <td>${item.label}</td>
                <td>₦ ${formatCurrency(item.current)}</td>
                <td>₦ ${formatCurrency(item.previous)}</td>
                <td class="status-positive">${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%</td>
            </tr>
        `;
    }).join('');
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
