(function () {
    'use strict';

    let growthData = null;

    function initGrowth() {
        const script = document.getElementById('growthDataJson');
        if (script) {
            try {
                growthData = JSON.parse(script.textContent);
            } catch (e) {
                console.error('Failed to parse growth data JSON', e);
            }
        }

        renderGrowthSummary();
        renderGrowthChart();
        renderDrivers();
        renderNotes();
    }

    function renderGrowthSummary() {
        const salesGrowth = Number(growthData?.sales_growth_percentage || 0);
        const profitGrowth = Number(growthData?.profit_growth_percentage || 0);
        const volumeGrowth = Number(growthData?.sales_volume_growth_percentage || 0);
        const currSales = Number(growthData?.current_period_sales || 0);
        const prevSales = Number(growthData?.previous_period_sales || 0);
        const currOrders = Number(growthData?.current_period_sales_count || 0);
        const prevOrders = Number(growthData?.previous_period_sales_count || 0);

        const avgGrowth = (salesGrowth + profitGrowth + volumeGrowth) / 3;

        const formatPct = (val) => `${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;

        document.getElementById('growthSales')?.replaceChildren(document.createTextNode(formatPct(salesGrowth)));
        document.getElementById('growthRevenue')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(currSales)}`));
        document.getElementById('growthCustomers')?.replaceChildren(document.createTextNode(formatPct(volumeGrowth)));
        document.getElementById('growthOrders')?.replaceChildren(document.createTextNode(`${currOrders} (prev: ${prevOrders})`));
        document.getElementById('growthProfit')?.replaceChildren(document.createTextNode(formatPct(profitGrowth)));
        document.getElementById('growthAverage')?.replaceChildren(document.createTextNode(formatPct(avgGrowth)));
    }

    function renderGrowthChart() {
        const chart = document.getElementById('growthChart');
        if (!chart) return;

        const currSales = Number(growthData?.current_period_sales || 0);
        const prevSales = Number(growthData?.previous_period_sales || 0);
        const currExp = Number(growthData?.current_period_expenses || 0);
        const currProfit = Number(growthData?.current_period_profit || 0);

        if (currSales === 0 && prevSales === 0 && currExp === 0) {
            chart.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted, #718096); width: 100%;">No sales or expense benchmark records in this period.</div>';
            return;
        }

        const maxVal = Math.max(currSales, prevSales, currExp, Math.abs(currProfit), 1);
        const points = [
            { label: 'Prev Revenue', value: prevSales },
            { label: 'Curr Revenue', value: currSales },
            { label: 'Expenses', value: currExp },
            { label: 'Net Profit', value: currProfit }
        ];

        chart.innerHTML = points.map(item => {
            const pct = Math.max(8, Math.min(100, Math.round((Math.abs(item.value) / maxVal) * 100)));
            return `
                <div class="growth-point">
                    <div class="growth-bar" style="height:${pct}%" title="₦ ${formatCurrency(item.value)}"></div>
                    <span>${escapeHtml(item.label)}</span>
                </div>
            `;
        }).join('');
    }

    function renderDrivers() {
        const drivers = document.getElementById('growthDrivers');
        if (!drivers) return;

        const salesGrowth = Number(growthData?.sales_growth_percentage || 0);
        const volumeGrowth = Number(growthData?.sales_volume_growth_percentage || 0);
        const expGrowth = Number(growthData?.expense_growth_percentage || 0);
        const profitGrowth = Number(growthData?.profit_growth_percentage || 0);

        const formatPct = (val) => `${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;

        const items = [
            { name: 'Revenue Momentum', value: formatPct(salesGrowth) },
            { name: 'Order Volume Velocity', value: formatPct(volumeGrowth) },
            { name: 'Expense Trajectory', value: formatPct(expGrowth) },
            { name: 'Profitability Margin Delta', value: formatPct(profitGrowth) }
        ];

        drivers.innerHTML = items.map(item => `
            <div class="growth-item">
                <strong>${escapeHtml(item.name)}</strong>
                <span>${escapeHtml(item.value)}</span>
            </div>
        `).join('');
    }

    function renderNotes() {
        const notes = document.getElementById('growthNotes');
        if (!notes) return;

        const currSales = Number(growthData?.current_period_sales || 0);
        const prevSales = Number(growthData?.previous_period_sales || 0);
        const salesGrowth = Number(growthData?.sales_growth_percentage || 0);
        const currOrders = Number(growthData?.current_period_sales_count || 0);

        const items = [];
        if (currOrders > 0) {
            items.push({
                title: 'Operating Activity',
                text: `${currOrders} sales transactions completed in the active period.`
            });
        } else {
            items.push({
                title: 'Activity Notice',
                text: 'No sales completed in this period. Metrics will update as transactions occur.'
            });
        }

        if (prevSales > 0) {
            items.push({
                title: 'Benchmark Variance',
                text: `Revenue changed by ${salesGrowth >= 0 ? '+' : ''}${salesGrowth.toFixed(1)}% compared to the prior operating window.`
            });
        } else {
            items.push({
                title: 'Benchmark Status',
                text: 'Initial benchmark window established. Historical comparison will expand with each operating cycle.'
            });
        }

        notes.innerHTML = items.map(note => `
            <div class="note-item">
                <strong>${escapeHtml(note.title)}</strong>
                <span>${escapeHtml(note.text)}</span>
            </div>
        `).join('');
    }

    function formatCurrency(value) {
        const num = Number(value || 0);
        return num.toLocaleString('en-NG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
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
        document.addEventListener('DOMContentLoaded', initGrowth);
    } else {
        initGrowth();
    }
    window.addEventListener('page:load', initGrowth);
})();
