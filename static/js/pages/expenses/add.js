/**
 * MADAM HY - Add expense interactions.
 * Frontend-only demo for expense recording.
 */

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('addExpenseForm');
    const expenseDate = document.getElementById('expenseDate');
    const expenseCategory = document.getElementById('expenseCategory');
    const expenseAmount = document.getElementById('expenseAmount');
    const expensePaymentMethod = document.getElementById('expensePaymentMethod');
    const expenseVendor = document.getElementById('expenseVendor');
    const summaryDate = document.getElementById('summaryDate');
    const summaryCategory = document.getElementById('summaryCategory');
    const summaryAmount = document.getElementById('summaryAmount');
    const summaryMethod = document.getElementById('summaryMethod');
    const summaryVendor = document.getElementById('summaryVendor');

    // Set today's date as default
    const today = new Date().toISOString().split('T')[0];
    if (expenseDate) expenseDate.value = today;

    // Update summary when form fields change
    const updateSummary = () => {
        if (summaryDate) summaryDate.textContent = expenseDate?.value ? formatDate(expenseDate.value) : '-';
        if (summaryCategory) summaryCategory.textContent = expenseCategory?.value || '-';
        if (summaryAmount) summaryAmount.textContent = `₦ ${formatCurrency(parseFloat(expenseAmount?.value) || 0)}`;
        if (summaryMethod) summaryMethod.textContent = expensePaymentMethod?.value || '-';
        if (summaryVendor) summaryVendor.textContent = expenseVendor?.value || '-';
    };

    expenseDate?.addEventListener('change', updateSummary);
    expenseCategory?.addEventListener('change', updateSummary);
    expenseAmount?.addEventListener('input', updateSummary);
    expensePaymentMethod?.addEventListener('change', updateSummary);
    expenseVendor?.addEventListener('input', updateSummary);

    // Initial summary update
    updateSummary();

    // Handle form submission
    form?.addEventListener('submit', (e) => {
        e.preventDefault();

        const date = expenseDate?.value;
        const category = expenseCategory?.value;
        const amount = parseFloat(expenseAmount?.value);
        const method = expensePaymentMethod?.value;
        const errorDiv = document.getElementById('formError');
        const successMsg = document.getElementById('successMessage');

        // Validation
        if (!date) {
            showError(errorDiv, 'Please select a date');
            return;
        }

        if (!category) {
            showError(errorDiv, 'Please select a category');
            return;
        }

        if (!amount || amount <= 0) {
            showError(errorDiv, 'Please enter a valid amount');
            return;
        }

        if (!method) {
            showError(errorDiv, 'Please select a payment method');
            return;
        }

        // Success - hide form, show success message
        form.style.display = 'none';
        successMsg?.classList.remove('hidden');
    });

    function showError(errorDiv, message) {
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.classList.remove('hidden');
            setTimeout(() => {
                errorDiv.classList.add('hidden');
            }, 4000);
        }
    }
});

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
