/**
 * MADAM HY - Expense detail interactions.
 * Frontend-only demo data for expense details view.
 */

const expenseDetailData = {
    id: 'EXP-001',
    date: '2026-08-14',
    category: 'Rent',
    description: 'Monthly shop rent payment for August 2026. This covers the main retail space and storage area as per lease agreement signed on 2024-01-15. Payment is due on the first of each month.',
    amount: 150000,
    vendor: 'Landmark Properties',
    paymentMethod: 'Transfer',
    reference: 'TRANS-142601-01',
    recordedBy: 'Aisha Bello',
    recordedOn: '2026-08-14',
    relatedExpenses: [
        { date: '2026-07-01', amount: 150000 },
        { date: '2026-06-01', amount: 150000 },
        { date: '2026-05-01', amount: 150000 }
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    const detailExpenseRef = document.getElementById('detailExpenseRef');
    const detailExpenseDate = document.getElementById('detailExpenseDate');
    const detailExpenseCategory = document.getElementById('detailExpenseCategory');
    const detailCategory = document.getElementById('detailCategory');
    const detailAmount = document.getElementById('detailAmount');
    const detailVendor = document.getElementById('detailVendor');
    const detailPaymentMethod = document.getElementById('detailPaymentMethod');
    const detailDescription = document.getElementById('detailDescription');
    const detailTransactionDate = document.getElementById('detailTransactionDate');
    const detailReference = document.getElementById('detailReference');
    const detailRecordedBy = document.getElementById('detailRecordedBy');
    const detailRecordedOn = document.getElementById('detailRecordedOn');
    const relatedCategoryTotal = document.getElementById('relatedCategoryTotal');
    const relatedCategoryCount = document.getElementById('relatedCategoryCount');
    const relatedExpensesBody = document.getElementById('relatedExpensesBody');

    if (detailExpenseRef) detailExpenseRef.textContent = expenseDetailData.id;
    if (detailExpenseDate) detailExpenseDate.textContent = formatDate(expenseDetailData.date);
    if (detailExpenseCategory) {
        detailExpenseCategory.textContent = expenseDetailData.category;
        detailExpenseCategory.className = `category-badge ${expenseDetailData.category.toLowerCase()}`;
    }
    if (detailCategory) detailCategory.textContent = expenseDetailData.category;
    if (detailAmount) detailAmount.textContent = `₦ ${formatCurrency(expenseDetailData.amount)}`;
    if (detailVendor) detailVendor.textContent = expenseDetailData.vendor;
    if (detailPaymentMethod) detailPaymentMethod.textContent = expenseDetailData.paymentMethod;
    if (detailDescription) detailDescription.textContent = expenseDetailData.description;
    if (detailTransactionDate) detailTransactionDate.textContent = formatDate(expenseDetailData.date);
    if (detailReference) detailReference.textContent = expenseDetailData.reference;
    if (detailRecordedBy) detailRecordedBy.textContent = expenseDetailData.recordedBy;
    if (detailRecordedOn) detailRecordedOn.textContent = formatDate(expenseDetailData.recordedOn);

    // Related expenses calculation
    const categoryTotal = expenseDetailData.relatedExpenses.reduce((sum, e) => sum + e.amount, 0) + expenseDetailData.amount;
    const categoryCount = expenseDetailData.relatedExpenses.length + 1;

    if (relatedCategoryTotal) relatedCategoryTotal.textContent = `₦ ${formatCurrency(categoryTotal)}`;
    if (relatedCategoryCount) relatedCategoryCount.textContent = String(categoryCount);

    if (relatedExpensesBody) {
        relatedExpensesBody.innerHTML = expenseDetailData.relatedExpenses.map(expense => `
            <tr>
                <td>${formatDate(expense.date)}</td>
                <td>₦ ${formatCurrency(expense.amount)}</td>
            </tr>
        `).join('');
    }
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
