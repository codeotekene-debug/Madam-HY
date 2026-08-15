/**
 * MADAM HY - Expenses list interactions.
 * Frontend-only demo data for expense browsing and filtering.
 */

const expensesData = [
    {
        id: 'EXP-001',
        date: '2026-08-14',
        category: 'Rent',
        description: 'Monthly shop rent payment for August',
        amount: 150000,
        vendor: 'Landmark Properties',
        paymentMethod: 'Transfer',
        reference: 'TRANS-142601-01'
    },
    {
        id: 'EXP-002',
        date: '2026-08-12',
        category: 'Utilities',
        description: 'Electric bill and water for the shop',
        amount: 15000,
        vendor: 'Power Distribution Company',
        paymentMethod: 'Cash',
        reference: 'BILL-082601'
    },
    {
        id: 'EXP-003',
        date: '2026-08-10',
        category: 'Supplies',
        description: 'Packaging materials and stationery stock',
        amount: 25000,
        vendor: 'ABC Supplies Ltd',
        paymentMethod: 'Transfer',
        reference: 'INV-08261'
    },
    {
        id: 'EXP-004',
        date: '2026-08-08',
        category: 'Maintenance',
        description: 'Air conditioning unit service and repair',
        amount: 18000,
        vendor: 'Cool Tech Services',
        paymentMethod: 'Cash',
        reference: 'RECEIPT-080826'
    },
    {
        id: 'EXP-005',
        date: '2026-08-05',
        category: 'Transport',
        description: 'Fuel for delivery van this week',
        amount: 8000,
        vendor: 'Shell Petrol Station',
        paymentMethod: 'Card',
        reference: 'FUEL-050826'
    },
    {
        id: 'EXP-006',
        date: '2026-08-01',
        category: 'Salaries',
        description: 'August salaries for shop staff (4 employees)',
        amount: 240000,
        vendor: 'Internal',
        paymentMethod: 'Transfer',
        reference: 'SAL-080126'
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderExpensesSummary();
    renderExpensesTable();
    bindExpensesFilters();
});

function bindExpensesFilters() {
    const searchInput = document.getElementById('expensesSearch');
    const categoryFilter = document.getElementById('expensesCategoryFilter');

    const update = () => renderExpensesTable();

    searchInput?.addEventListener('input', update);
    categoryFilter?.addEventListener('change', update);
}

function renderExpensesSummary() {
    const totalExpenses = document.getElementById('totalExpenses');
    const monthExpenses = document.getElementById('monthExpenses');
    const yearExpenses = document.getElementById('yearExpenses');
    const topCategory = document.getElementById('topCategory');

    const total = expensesData.reduce((sum, e) => sum + e.amount, 0);

    const currentMonth = new Date().getMonth();
    const currentYear = new Date().getFullYear();

    const monthTotal = expensesData
        .filter(e => {
            const date = new Date(e.date);
            return date.getMonth() === currentMonth && date.getFullYear() === currentYear;
        })
        .reduce((sum, e) => sum + e.amount, 0);

    const yearTotal = expensesData
        .filter(e => new Date(e.date).getFullYear() === currentYear)
        .reduce((sum, e) => sum + e.amount, 0);

    // Find top category
    const categoryTotals = {};
    expensesData.forEach(e => {
        categoryTotals[e.category] = (categoryTotals[e.category] || 0) + e.amount;
    });
    const topCat = Object.entries(categoryTotals).sort((a, b) => b[1] - a[1])[0]?.[0] || '-';

    if (totalExpenses) totalExpenses.textContent = `₦ ${formatCurrency(total)}`;
    if (monthExpenses) monthExpenses.textContent = `₦ ${formatCurrency(monthTotal)}`;
    if (yearExpenses) yearExpenses.textContent = `₦ ${formatCurrency(yearTotal)}`;
    if (topCategory) topCategory.textContent = topCat;
}

function renderExpensesTable() {
    const tableBody = document.getElementById('expensesTableBody');
    const emptyState = document.getElementById('expensesEmptyState');
    const searchInput = document.getElementById('expensesSearch');
    const categoryFilter = document.getElementById('expensesCategoryFilter');

    if (!tableBody) return;

    const query = searchInput?.value.trim().toLowerCase() || '';
    const categoryValue = categoryFilter?.value || 'all';

    let filtered = expensesData.filter(expense => {
        const matchesQuery = !query || [expense.description, expense.category].some(value =>
            value.toLowerCase().includes(query)
        );
        const matchesCategory = categoryValue === 'all' || expense.category === categoryValue;
        return matchesQuery && matchesCategory;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(expense => `
        <tr>
            <td data-label="Date">${formatDate(expense.date)}</td>
            <td data-label="Category"><span class="category-badge ${expense.category.toLowerCase()}">${expense.category}</span></td>
            <td data-label="Description">${expense.description}</td>
            <td data-label="Amount">₦ ${formatCurrency(expense.amount)}</td>
            <td data-label="Vendor">${expense.vendor}</td>
            <td data-label="Reference">${expense.reference}</td>
            <td data-label="Action"><a href="#" class="action-link">View</a></td>
        </tr>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
