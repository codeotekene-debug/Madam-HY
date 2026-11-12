(function () {
    'use strict';

    let salesData = null;
    let salesReportData = [];

    function initSales() {
        const script = document.getElementById('salesDataJson');
        if (script) {
            try {
                salesData = JSON.parse(script.textContent);
            } catch (e) {
                console.error('Failed to parse sales data JSON', e);
            }
        }

        salesReportData = (salesData && salesData.recent_sales) ? salesData.recent_sales : [];

        renderSalesSummary();
        renderSalesTrend();
        renderPaymentMix();
        renderSalesTable();

        const filterSelect = document.getElementById('salesMethodFilter');
        filterSelect?.addEventListener('change', renderSalesTable);

        const urlParams = new URLSearchParams(window.location.search);
        const currentPeriod = urlParams.get('period') || 'this_month';

        document.querySelectorAll('.range-button').forEach(button => {
            const range = button.dataset.range;
            if (
                (range === 'month' && (currentPeriod === 'this_month' || currentPeriod === 'month')) ||
                (range === 'quarter' && (currentPeriod === 'this_quarter' || currentPeriod === 'quarter')) ||
                (range === 'year' && (currentPeriod === 'this_year' || currentPeriod === 'year')) ||
                (range === 'today' && currentPeriod === 'today')
            ) {
                document.querySelectorAll('.range-button').forEach(item => item.classList.remove('active'));
                button.classList.add('active');
            }

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

        document.getElementById('exportSalesCsvBtn')?.addEventListener('click', () => {
            if (!salesReportData.length) {
                alert('No sales records to export for this period.');
                return;
            }
            const headers = ['Date', 'Invoice', 'Payment Method', 'Customer', 'Revenue (NGN)', 'Items Count'];
            const rows = salesReportData.map(row => [
                `"${row.date || ''}"`,
                `"${row.invoice || ''}"`,
                `"${row.payment || ''}"`,
                `"${row.customer || ''}"`,
                `"${row.revenue || 0}"`,
                `"${row.items || 0}"`,
            ]);
            const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement('a');
            link.setAttribute('href', encodedUri);
            link.setAttribute('download', `sales_report_${currentPeriod}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    function renderSalesSummary() {
        const total = salesData ? Number(salesData.total_sales || 0) : salesReportData.reduce((sum, row) => sum + Number(row.revenue || 0), 0);
        const count = salesData ? Number(salesData.sales_count || 0) : salesReportData.length;
        const avg = salesData ? Number(salesData.average_sale || 0) : (count > 0 ? total / count : 0);

        document.getElementById('salesTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));
        document.getElementById('salesTransactions')?.replaceChildren(document.createTextNode(String(count)));
        document.getElementById('salesAverage')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(avg)}`));
        document.getElementById('salesGrowth')?.replaceChildren(document.createTextNode(count > 0 ? `${count} orders` : '-'));
    }

    function renderSalesTrend() {
        const chart = document.getElementById('salesTrendChart');
        if (!chart) return;

        const days = (salesData && salesData.sales_by_day) ? salesData.sales_by_day : [];
        if (!days.length) {
            chart.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted, #718096); width: 100%;">No sales recorded in this period.</div>';
            return;
        }

        const maxVal = Math.max(...days.map(d => Number(d.total_sales || 0))) || 1;
        chart.innerHTML = days.slice(-8).map(d => {
            const pct = Math.max(8, Math.min(100, Math.round((Number(d.total_sales || 0) / maxVal) * 100)));
            const label = d.day ? String(d.day).slice(5) : '';
            return `
                <div class="bar-segment" style="--value: ${pct}%" title="₦ ${formatCurrency(d.total_sales)}">
                    <span>${escapeHtml(label)}</span>
                </div>
            `;
        }).join('');
    }

    function renderPaymentMix() {
        const mix = document.getElementById('salesPaymentMix');
        if (!mix) return;

        const methods = (salesData && salesData.sales_by_payment_method) ? salesData.sales_by_payment_method : [];
        if (!methods.length) {
            mix.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted, #718096); width: 100%;">No payment channel data available.</div>';
            return;
        }

        const total = methods.reduce((sum, item) => sum + Number(item.total_sales || 0), 0) || 1;

        mix.innerHTML = methods.map(item => {
            const val = Number(item.total_sales || 0);
            const pct = ((val / total) * 100).toFixed(1);
            return `
                <div class="payment-item">
                    <div>
                        <strong>${escapeHtml(item.payment_method)}</strong>
                    </div>
                    <span>${pct}% · ₦ ${formatCurrency(val)}</span>
                </div>
            `;
        }).join('');
    }

    function renderSalesTable() {
        const tableBody = document.getElementById('salesTableBody');
        const emptyState = document.getElementById('salesEmptyState');
        const methodFilter = (document.getElementById('salesMethodFilter')?.value || 'all').toUpperCase();

        if (!tableBody) return;

        const filtered = salesReportData.filter(item => methodFilter === 'ALL' || String(item.payment || '').toUpperCase() === methodFilter);

        if (!filtered.length) {
            tableBody.innerHTML = '';
            emptyState?.classList.remove('empty-state-hidden');
            return;
        }

        emptyState?.classList.add('empty-state-hidden');
        tableBody.innerHTML = filtered.map(item => `
            <tr>
                <td>${formatDate(item.date)}</td>
                <td>${escapeHtml(item.invoice)}</td>
                <td>${escapeHtml(item.payment)}</td>
                <td>${escapeHtml(item.customer)}</td>
                <td>₦ ${formatCurrency(item.revenue)}</td>
                <td>${item.items}</td>
            </tr>
        `).join('');
    }

    function formatDate(value) {
        if (!value) return '-';
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
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
        document.addEventListener('DOMContentLoaded', initSales);
    } else {
        initSales();
    }
    window.addEventListener('page:load', initSales);
})();
