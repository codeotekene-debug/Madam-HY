const salesReportData = [
    { date: '2026-08-01', invoice: 'INV-10241', payment: 'Cash', customer: 'Aisha Bello', revenue: 42500, items: 3 },
    { date: '2026-08-02', invoice: 'INV-10242', payment: 'Card', customer: 'Musa Adamu', revenue: 31800, items: 4 },
    { date: '2026-08-04', invoice: 'INV-10243', payment: 'Transfer', customer: 'Grace Nnaji', revenue: 28000, items: 2 },
    { date: '2026-08-06', invoice: 'INV-10244', payment: 'Card', customer: 'Emeka Ibe', revenue: 36500, items: 5 },
    { date: '2026-08-09', invoice: 'INV-10245', payment: 'Cash', customer: 'Sade Okon', revenue: 41000, items: 3 },
    { date: '2026-08-12', invoice: 'INV-10246', payment: 'Transfer', customer: 'Tunde Babs', revenue: 47200, items: 4 }
];

document.addEventListener('DOMContentLoaded', () => {
    renderSalesSummary();
    renderSalesTrend();
    renderPaymentMix();
    renderSalesTable();

    const filterSelect = document.getElementById('salesMethodFilter');
    filterSelect?.addEventListener('change', renderSalesTable);

    document.querySelectorAll('.range-button').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.range-button').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
        });
    });
});

function renderSalesSummary() {
    const total = salesReportData.reduce((sum, row) => sum + row.revenue, 0);
    const avg = total / salesReportData.length;

    document.getElementById('salesTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));
    document.getElementById('salesTransactions')?.replaceChildren(document.createTextNode(String(salesReportData.length)));
    document.getElementById('salesAverage')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(avg)}`));
    document.getElementById('salesGrowth')?.replaceChildren(document.createTextNode('+18.4%'));
}

function renderSalesTrend() {
    const chart = document.getElementById('salesTrendChart');
    if (!chart) return;

    const values = [40, 52, 58, 74, 68, 85];
    chart.innerHTML = values.map((value, index) => `
        <div class="bar-segment" style="--value: ${value}%">
            <span>${['W1','W2','W3','W4','W5','W6'][index]}</span>
        </div>
    `).join('');
}

function renderPaymentMix() {
    const mix = document.getElementById('salesPaymentMix');
    if (!mix) return;

    const paymentTotals = {
        Cash: salesReportData.filter(item => item.payment === 'Cash').reduce((sum, item) => sum + item.revenue, 0),
        Card: salesReportData.filter(item => item.payment === 'Card').reduce((sum, item) => sum + item.revenue, 0),
        Transfer: salesReportData.filter(item => item.payment === 'Transfer').reduce((sum, item) => sum + item.revenue, 0)
    };

    const total = Object.values(paymentTotals).reduce((sum, value) => sum + value, 0);

    mix.innerHTML = Object.entries(paymentTotals).map(([method, value]) => `
        <div class="payment-item">
            <div>
                <strong>${method}</strong>
            </div>
            <span>${((value / total) * 100).toFixed(1)}% · ₦ ${formatCurrency(value)}</span>
        </div>
    `).join('');
}

function renderSalesTable() {
    const tableBody = document.getElementById('salesTableBody');
    const emptyState = document.getElementById('salesEmptyState');
    const methodFilter = document.getElementById('salesMethodFilter')?.value || 'all';

    if (!tableBody) return;

    const filtered = salesReportData.filter(item => methodFilter === 'all' || item.payment === methodFilter);

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(item => `
        <tr>
            <td>${formatDate(item.date)}</td>
            <td>${item.invoice}</td>
            <td>${item.payment}</td>
            <td>${item.customer}</td>
            <td>₦ ${formatCurrency(item.revenue)}</td>
            <td>${item.items}</td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
