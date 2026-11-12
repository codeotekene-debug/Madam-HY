(function () {
    'use strict';

    function initReports() {
        const overviewScript = document.getElementById('overviewDataJson');
        const growthScript = document.getElementById('growthReportJson');
        const chartScript = document.getElementById('revenueChartDataJson');

        let data = null;
        let growth = null;
        let chartData = [];
        if (overviewScript) {
            try {
                data = JSON.parse(overviewScript.textContent);
            } catch (e) {
                console.error('Failed to parse overview data JSON', e);
            }
        }
        if (growthScript) {
            try {
                growth = JSON.parse(growthScript.textContent);
            } catch (e) {
                console.error('Failed to parse growth data JSON', e);
            }
        }
        if (chartScript) {
            try {
                chartData = JSON.parse(chartScript.textContent) || [];
            } catch (e) {
                console.error('Failed to parse revenue chart data', e);
            }
        }

        if (!data) {
            data = {
                total_sales: 0,
                total_expenses: 0,
                gross_profit: 0,
                net_profit: 0,
                transactions: 0,
                aov: 0,
                comparison: 0,
                top_category: '-',
                expense_ratio: 0,
                profit_margin: 0,
                customer_growth: 0
            };
        }

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

        renderRevenueChart(chartData);

        const salesVal = Number(data.total_sales || 0);
        const expVal = Number(data.total_expenses || 0);
        const grossVal = Number(data.gross_profit || 0);
        const netVal = Number(data.net_profit || 0);
        const txCount = Number(data.transactions || 0);
        const aovVal = Number(data.aov || 0);
        const compVal = Number(data.comparison || 0);
        const expRatioVal = Number(data.expense_ratio || 0);
        const marginVal = Number(data.profit_margin || 0);
        const custGrowthVal = Number(data.customer_growth || 0);

        if (totalSales) totalSales.textContent = `₦ ${formatCurrency(salesVal)}`;
        if (totalExpenses) totalExpenses.textContent = `₦ ${formatCurrency(expVal)}`;
        if (grossProfit) grossProfit.textContent = `₦ ${formatCurrency(grossVal)}`;
        if (netProfit) netProfit.textContent = `₦ ${formatCurrency(netVal)}`;
        if (transactions) transactions.textContent = formatNumber(txCount);
        if (aov) aov.textContent = `₦ ${formatCurrency(aovVal)}`;
        if (comparison) comparison.textContent = `${compVal > 0 ? '+' : ''}${compVal.toFixed(1)}%`;
        if (topCategory) topCategory.textContent = data.top_category || '-';
        if (expenseRatio) expenseRatio.textContent = `${expRatioVal.toFixed(1)}%`;
        if (profitMargin) profitMargin.textContent = `${marginVal.toFixed(1)}%`;
        if (customerGrowth) customerGrowth.textContent = `${custGrowthVal > 0 ? '+' : ''}${custGrowthVal.toFixed(1)}%`;

        if (tableBody) {
            const currentSales = salesVal;
            const prevSales = growth ? Number(growth.previous_period_sales || 0) : 0;
            const salesDiff = growth ? Number(growth.sales_growth_percentage || 0) : 0;

            const currentOrders = growth ? Number(growth.current_period_sales_count || 0) : txCount;
            const prevOrders = growth ? Number(growth.previous_period_sales_count || 0) : 0;
            const ordersDiff = growth ? Number(growth.sales_volume_growth_percentage || 0) : 0;
            const prevExpenses = growth ? Number(growth.previous_period_expenses || 0) : 0;
            const prevNet = growth ? Number(growth.previous_period_profit || 0) : 0;
            const expenseDiff = growth ? Number(growth.expense_growth_percentage || 0) : 0;
            const profitDiff = growth ? Number(growth.profit_growth_percentage || 0) : 0;

            const rows = [
                {
                    metric: 'Revenue',
                    current: `₦ ${formatCurrency(currentSales)}`,
                    previous: `₦ ${formatCurrency(prevSales)}`,
                    change: `${salesDiff >= 0 ? '+' : ''}${salesDiff.toFixed(1)}%`,
                    isPositive: salesDiff >= 0
                },
                {
                    metric: 'Operating Expenses',
                    current: `₦ ${formatCurrency(expVal)}`,
                    previous: `₦ ${formatCurrency(prevExpenses)}`,
                    change: `${expenseDiff >= 0 ? '+' : ''}${expenseDiff.toFixed(1)}%`,
                    isPositive: expenseDiff <= 0
                },
                {
                    metric: 'Net Profit Margin',
                    current: `₦ ${formatCurrency(netVal)}`,
                    previous: `₦ ${formatCurrency(prevNet)}`,
                    change: `${profitDiff >= 0 ? '+' : ''}${profitDiff.toFixed(1)}%`,
                    isPositive: profitDiff >= 0
                },
                {
                    metric: 'Transaction Count',
                    current: formatNumber(currentOrders),
                    previous: formatNumber(prevOrders),
                    change: `${ordersDiff >= 0 ? '+' : ''}${ordersDiff.toFixed(1)}%`,
                    isPositive: ordersDiff >= 0
                }
            ];

            tableBody.innerHTML = rows.map(row => `
                <tr>
                    <th scope="row">${escapeHtml(row.metric)}</th>
                    <td class="num">${escapeHtml(row.current)}</td>
                    <td class="num">${escapeHtml(row.previous)}</td>
                    <td class="text-right ${row.isPositive ? 'status-positive' : 'status-negative'}">${escapeHtml(row.change)}</td>
                </tr>
            `).join('');
        }

        const urlParams = new URLSearchParams(window.location.search);
        const currentPeriod = urlParams.get('period') || 'this_month';

        const buttons = document.querySelectorAll('.range-button');
        buttons.forEach(button => {
            const range = button.dataset.range;
            const selected =
                (range === 'month' && (currentPeriod === 'this_month' || currentPeriod === 'month')) ||
                (range === 'quarter' && (currentPeriod === 'this_quarter' || currentPeriod === 'quarter')) ||
                (range === 'year' && (currentPeriod === 'this_year' || currentPeriod === 'year'));
            button.classList.toggle('active', selected);
            button.setAttribute('aria-pressed', String(selected));

            button.addEventListener('click', () => {
                let p = 'this_month';
                if (range === 'quarter') p = 'this_quarter';
                else if (range === 'year') p = 'this_year';
                else if (range === 'today') p = 'today';
                const url = new URL(window.location.href);
                url.searchParams.set('period', p);
                window.location.href = url.toString();
            });
        });
    }

    function renderRevenueChart(points) {
        const chart = document.getElementById('overviewChart');
        const empty = document.getElementById('overviewChartEmpty');
        const tableBody = document.querySelector('#overviewChartDataTable tbody');
        if (!chart) return;

        const hasRevenue = points.some(point => Number(point.revenue) > 0);
        chart.replaceChildren();
        if (tableBody) tableBody.replaceChildren();
        if (!hasRevenue) {
            chart.hidden = true;
            if (empty) empty.hidden = false;
            chart.setAttribute('aria-label', 'No completed sales revenue recorded for this period');
            return;
        }

        if (empty) empty.hidden = true;
        chart.hidden = false;
        chart.style.minWidth = `${Math.max(chart.parentElement.clientWidth, points.length * 34)}px`;
        const description = [];
        points.forEach(point => {
            const amount = Number(point.revenue) || 0;
            const bar = document.createElement('div');
            bar.className = 'chart-bar';
            bar.style.setProperty('--value', `${Math.max(Number(point.bar_percent) || 0, amount ? 3 : 0)}%`);
            bar.title = `${point.label}: ₦ ${formatCurrency(amount)}`;
            bar.setAttribute('aria-hidden', 'true');
            const label = document.createElement('span');
            label.textContent = point.label;
            bar.append(label);
            chart.append(bar);
            description.push(`${point.label}: ₦ ${formatCurrency(amount)}`);

            if (tableBody) {
                const row = document.createElement('tr');
                const labelCell = document.createElement('th');
                labelCell.scope = 'row';
                labelCell.textContent = point.label;
                const valueCell = document.createElement('td');
                valueCell.textContent = `₦ ${formatCurrency(amount)}`;
                row.append(labelCell, valueCell);
                tableBody.append(row);
            }
        });
        chart.setAttribute('aria-label', `Completed sales revenue: ${description.join('; ')}`);
    }

    function formatCurrency(value) {
        return new Intl.NumberFormat('en-NG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(Number(value) || 0);
    }

    function formatNumber(value) {
        return Number(value).toLocaleString('en-NG');
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initReports);
    } else {
        initReports();
    }
    window.addEventListener('page:load', initReports);
})();
