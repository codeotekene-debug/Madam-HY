/**
 * MADAM HY - Credit payment interactions.
 * Frontend-only demo for credit payment processing.
 */

const customerCredits = {
    'aisha-bello': { name: 'Aisha Bello', balance: 50000 },
    'musa-adamu': { name: 'Musa Adamu', balance: 0 },
    'grace-nnaji': { name: 'Grace Nnaji', balance: 47500 },
    'emeka-ibe': { name: 'Emeka Ibe', balance: 50000 },
    'zainab-hassan': { name: 'Zainab Hassan', balance: 50000 },
    'james-obi': { name: 'James Obi', balance: 0 }
};

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('creditPaymentForm');
    const customerSelect = document.getElementById('paymentCustomer');
    const paymentAmount = document.getElementById('paymentAmount');
    const summaryCustomer = document.getElementById('summaryCustomer');
    const summaryCurrentBalance = document.getElementById('summaryCurrentBalance');
    const summaryPaymentAmount = document.getElementById('summaryPaymentAmount');
    const summaryRemainingBalance = document.getElementById('summaryRemainingBalance');

    // Update summary when customer changes
    customerSelect?.addEventListener('change', () => {
        const customerId = customerSelect.value;
        if (customerId && customerCredits[customerId]) {
            const customer = customerCredits[customerId];
            summaryCustomer.textContent = customer.name;
            summaryCurrentBalance.textContent = `₦ ${formatCurrency(customer.balance)}`;
            paymentAmount.value = '';
            summaryPaymentAmount.textContent = '₦ 0';
            summaryRemainingBalance.textContent = `₦ ${formatCurrency(customer.balance)}`;
        }
    });

    // Update summary when payment amount changes
    paymentAmount?.addEventListener('input', () => {
        const customerId = customerSelect.value;
        if (!customerId || !customerCredits[customerId]) {
            summaryPaymentAmount.textContent = '₦ 0';
            summaryRemainingBalance.textContent = '₦ 0';
            return;
        }

        const customer = customerCredits[customerId];
        const amount = parseFloat(paymentAmount.value) || 0;
        const remaining = Math.max(0, customer.balance - amount);

        summaryPaymentAmount.textContent = `₦ ${formatCurrency(amount)}`;
        summaryRemainingBalance.textContent = `₦ ${formatCurrency(remaining)}`;
    });

    // Handle form submission
    form?.addEventListener('submit', (e) => {
        e.preventDefault();

        const customerId = customerSelect.value;
        const method = document.getElementById('paymentMethod').value;
        const amount = parseFloat(paymentAmount.value);
        const errorDiv = document.getElementById('formError');
        const successMsg = document.getElementById('successMessage');

        // Validation
        if (!customerId) {
            showError(errorDiv, 'Please select a customer');
            return;
        }

        if (!method) {
            showError(errorDiv, 'Please select a payment method');
            return;
        }

        if (!amount || amount <= 0) {
            showError(errorDiv, 'Please enter a valid payment amount');
            return;
        }

        const customer = customerCredits[customerId];
        if (amount > customer.balance) {
            showError(errorDiv, `Payment amount cannot exceed outstanding balance of ₦ ${formatCurrency(customer.balance)}`);
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

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
