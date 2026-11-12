(function () {
    'use strict';

    let expenseData = null;
    let expenseReportData = [];

    function initExpense() {
        const script = document.getElementById('expenseDataJson');
        if (script) {
            try {
                expenseData = JSON.parse(script.textContent);
            } catch (e) {
                console.error('Failed to parse expense data JSON', e);
            }
        }

        expenseReportData = (expenseData && expenseData.recent_expenses) ? expenseData.recent_expenses : [];

        renderExpenseSummary();
        renderTrendChart();
        renderCategoryList();
        renderExpenseTable();
    }

    function renderExpenseSummary() {
        const total = expenseData ? Number(expenseData.total_expenses || 0) : expenseReportData.reduce((sum, item) => sum + Number(item.amount || 0), 0);
        const count = expenseData ? Number(expenseData.expense_count || 0) : expenseReportData.length;
        const average = count > 0 ? (total / count) : 0;

        const categories = (expenseData && expenseData.expenses_by_category) ? expenseData.expenses_by_category : [];
        const topCat = categories.length ? categories[0].category : '-';

        document.getElementById('expenseTotal')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(total)}`));
        document.getElementById('expenseAverage')?.replaceChildren(document.createTextNode(`₦ ${formatCurrency(average)}`));
        document.getElementById('expenseTopCategory')?.replaceChildren(document.createTextNode(topCat));
        document.getElementById('expenseGrowth')?.replaceChildren(document.createTextNode(count > 0 ? `${count} records` : '-'));
    }

    function renderTrendChart() {
        const chart = document.getElementById('expenseTrendChart');
        if (!chart) return;

        const days = (expenseData && expenseData.expenses_by_day) ? expenseData.expenses_by_day : [];
        if (!days.length) {
            chart.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted, #718096); width: 100%;">No expense activity recorded in this period.</div>';
            return;
        }

        const maxVal = Math.max(...days.map(d => Number(d.total_expenses || 0))) || 1;
        chart.innerHTML = days.slice(-8).map(d => {
            const pct = Math.max(8, Math.min(100, Math.round((Number(d.total_expenses || 0) / maxVal) * 100)));
            const label = d.day ? String(d.day).slice(5) : '';
            return `
                <div class="bar-segment" style="--value: ${pct}%" title="₦ ${formatCurrency(d.total_expenses)}">
                    <span>${escapeHtml(label)}</span>
                </div>
            `;
        }).join('');
    }

    function renderCategoryList() {
        const container = document.getElementById('expenseCategoryList');
        if (!container) return;

        const categories = (expenseData && expenseData.expenses_by_category) ? expenseData.expenses_by_category : [];
        if (!categories.length) {
            container.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted, #718096);">No category breakdown available.</div>';
            return;
        }

        const total = categories.reduce((sum, item) => sum + Number(item.total_expenses || 0), 0) || 1;
        container.innerHTML = categories.map(item => {
            const amt = Number(item.total_expenses || 0);
            const pct = ((amt / total) * 100).toFixed(1);
            return `
                <div class="category-item">
                    <strong>${escapeHtml(item.category)}</strong>
                    <span>${pct}% · ₦ ${formatCurrency(amt)}</span>
                </div>
            `;
        }).join('');
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
                <td>${escapeHtml(item.category)}</td>
                <td>${escapeHtml(item.description || '-')}</td>
                <td>${escapeHtml(item.vendor || '-')}</td>
                <td>${formatDate(item.expense_date)}</td>
                <td>₦ ${formatCurrency(item.amount)}</td>
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
        document.addEventListener('DOMContentLoaded', initExpense);
    } else {
        initExpense();
    }
    window.addEventListener('page:load', initExpense);
})();
