const reportOverviewData = {
    totalSales: 12650000,
    totalExpenses: 4825000,
    grossProfit: 7835000,
    netProfit: 6245000,
    transactions: 428,
    aov: 29560,
    comparison: 14.6,
    topCategory: 'Home goods',
    expenseRatio: 38.2,
    profitMargin: 49.4,
    customerGrowth: 12.1
};

const overviewTableRows = [
    { metric: 'Revenue', current: '₦ 12,650,000', previous: '₦ 10,930,000', change: '+15.7%' },
    { metric: 'Expense ratio', current: '38.2%', previous: '41.4%', change: '-3.2%' },
    { metric: 'Profit margin', current: '49.4%', previous: '45.1%', change: '+4.3%' },
    { metric: 'Customer count', current: '1,420', previous: '1,240', change: '+14.5%' }
];

document.addEventListener('DOMContentLoaded', () => {
    const totalSales = document.getElementById('overviewTotalSales');
    const totalExpenses = document.getElementById('overviewTotalExpenses');
    const grossProfit = document.getElementById('overviewGrossProfit');
    const netProfit = document.getElementById('overviewNetProfit');
    const transactions = document.getElementById('overviewTransactions');
    const aov = document.getElementById('overviewAov');
    const comparison = document.getElementById('overviewComparison');
    const topCategory = document.getElementById('overviewTopCategory');
    const expenseRatio = document.getElementById('overviewExpenseRatio');
    const profitMargin = document.getElementById('overviewProfitMargin');
    const customerGrowth = document.getElementById('overviewCustomerGrowth');
    const tableBody = document.getElementById('overviewTableBody');

    if (totalSales) totalSales.textContent = `₦ ${formatCurrency(reportOverviewData.totalSales)}`;
    if (totalExpenses) totalExpenses.textContent = `₦ ${formatCurrency(reportOverviewData.totalExpenses)}`;
    if (grossProfit) grossProfit.textContent = `₦ ${formatCurrency(reportOverviewData.grossProfit)}`;
    if (netProfit) netProfit.textContent = `₦ ${formatCurrency(reportOverviewData.netProfit)}`;
    if (transactions) transactions.textContent = formatNumber(reportOverviewData.transactions);
    if (aov) aov.textContent = `₦ ${formatCurrency(reportOverviewData.aov)}`;
    if (comparison) comparison.textContent = `${reportOverviewData.comparison > 0 ? '+' : ''}${reportOverviewData.comparison.toFixed(1)}%`;
    if (topCategory) topCategory.textContent = reportOverviewData.topCategory;
    if (expenseRatio) expenseRatio.textContent = `${reportOverviewData.expenseRatio.toFixed(1)}%`;
    if (profitMargin) profitMargin.textContent = `${reportOverviewData.profitMargin.toFixed(1)}%`;
    if (customerGrowth) customerGrowth.textContent = `${reportOverviewData.customerGrowth > 0 ? '+' : ''}${reportOverviewData.customerGrowth.toFixed(1)}%`;

    if (tableBody) {
        tableBody.innerHTML = overviewTableRows.map(row => `
            <tr>
                <td>${row.metric}</td>
                <td>${row.current}</td>
                <td>${row.previous}</td>
                <td class="status-positive">${row.change}</td>
            </tr>
        `).join('');
    }

    const buttons = document.querySelectorAll('.range-button');
    buttons.forEach(button => {
        button.addEventListener('click', () => {
            buttons.forEach(item => item.classList.remove('active'));
            button.classList.add('active');
        });
    });
});

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}

function formatNumber(value) {
    return Number(value).toLocaleString('en-NG');
}
