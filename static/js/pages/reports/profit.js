(function () {
    'use strict';

    let profitData = null;

    function initProfit() {
        const script = document.getElementById('profitDataJson');
        if (script) {
            try {
                profitData = JSON.parse(script.textContent);
            } catch (e) {
                console.error('Failed to parse profit data JSON', e);
            }
        }

        renderProfitSummary();
        renderTrendChart();
        renderTable();
    }

    function renderProfitSummary() {
        const revenue = Number(profitData?.revenue || 0);
        const cost = Number(profitData?.cost_of_goods_sold || 0);
        const gross = Number(profitData?.gross_profit || 0);
        const expenses = Number(profitData?.expenses || 0);
        const net = Number(profitData?.net_profit || 0);
        const margin = Number(profitData?.profit_margin || (revenue > 0 ? (net / revenue) * 100 : 0));

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

        const revenue = Number(profitData?.revenue || 0);
        const gross = Number(profitData?.gross_profit || 0);
        const net = Number(profitData?.net_profit || 0);
        const expenses = Number(profitData?.expenses || 0);

        if (revenue === 0 && expenses === 0 && net === 0) {
            chart.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted, #718096); width: 100%;">No financial data recorded for this period.</div>';
            return;
        }

        const maxVal = Math.max(revenue, Math.abs(gross), Math.abs(net), expenses, 1);
        const points = [
            { label: 'Revenue', value: revenue },
            { label: 'Gross', value: gross },
            { label: 'Expenses', value: expenses },
            { label: 'Net Profit', value: net }
        ];

        chart.innerHTML = points.map(item => {
            const pct = Math.max(8, Math.min(100, Math.round((Math.abs(item.value) / maxVal) * 100)));
            return `
                <div class="trend-item">
                    <div class="trend-bar" style="height:${pct}%" title="₦ ${formatCurrency(item.value)}"></div>
                    <span>${escapeHtml(item.label)}</span>
                </div>
            `;
        }).join('');
    }

    function renderTable() {
        const tableBody = document.getElementById('profitTableBody');
        if (!tableBody) return;

        const revenue = Number(profitData?.revenue || 0);
        const cost = Number(profitData?.cost_of_goods_sold || 0);
        const gross = Number(profitData?.gross_profit || 0);
        const expenses = Number(profitData?.expenses || 0);
        const net = Number(profitData?.net_profit || 0);

        const rows = [
            { label: 'Gross Revenue', current: revenue, note: '100% of sales' },
            { label: 'Cost of Goods Sold (COGS)', current: cost, note: revenue > 0 ? `${((cost / revenue) * 100).toFixed(1)}% of rev` : '-' },
            { label: 'Gross Profit', current: gross, note: revenue > 0 ? `${((gross / revenue) * 100).toFixed(1)}% margin` : '-' },
            { label: 'Operating Expenses', current: expenses, note: revenue > 0 ? `${((expenses / revenue) * 100).toFixed(1)}% of rev` : '-' },
            { label: 'Net Profit', current: net, note: revenue > 0 ? `${((net / revenue) * 100).toFixed(1)}% margin` : '-' }
        ];

        tableBody.innerHTML = rows.map(item => `
            <tr>
                <td>${escapeHtml(item.label)}</td>
                <td>₦ ${formatCurrency(item.current)}</td>
                <td>-</td>
                <td class="${item.current >= 0 ? 'status-positive' : 'status-negative'}">${escapeHtml(item.note)}</td>
            </tr>
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
        document.addEventListener('DOMContentLoaded', initProfit);
    } else {
        initProfit();
    }
    window.addEventListener('page:load', initProfit);
})();
