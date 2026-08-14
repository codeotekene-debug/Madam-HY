document.addEventListener('DOMContentLoaded', () => {
    const receipt = JSON.parse(localStorage.getItem('madamHyReceipt') || 'null');
    const itemTable = document.getElementById('receiptItems');
    const receiptNumber = document.getElementById('receiptNumber');
    const receiptDate = document.getElementById('receiptDate');
    const receiptCashier = document.getElementById('receiptCashier');
    const receiptSubtotal = document.getElementById('receiptSubtotal');
    const receiptDiscount = document.getElementById('receiptDiscount');
    const receiptTotal = document.getElementById('receiptTotal');
    const receiptPayment = document.getElementById('receiptPayment');
    const receiptChange = document.getElementById('receiptChange');

    if (!receipt) {
        if (receiptNumber) receiptNumber.textContent = 'N/A';
        if (receiptDate) receiptDate.textContent = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
        if (receiptCashier) receiptCashier.textContent = 'Amina Yusuf';
        if (receiptSubtotal) receiptSubtotal.textContent = '₦ 0';
        if (receiptDiscount) receiptDiscount.textContent = '₦ 0';
        if (receiptTotal) receiptTotal.textContent = '₦ 0';
        if (receiptPayment) receiptPayment.textContent = 'Cash';
        if (receiptChange) receiptChange.textContent = '₦ 0';
        return;
    }

    if (itemTable) {
        itemTable.innerHTML = receipt.items.map(item => `
            <tr>
                <td>${item.name}</td>
                <td>${item.qty}</td>
                <td>₦ ${formatCurrency(item.total)}</td>
            </tr>
        `).join('');
    }

    if (receiptNumber) receiptNumber.textContent = receipt.number || 'N/A';
    if (receiptDate) receiptDate.textContent = receipt.date || new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    if (receiptCashier) receiptCashier.textContent = receipt.cashier || 'Amina Yusuf';
    if (receiptSubtotal) receiptSubtotal.textContent = `₦ ${formatCurrency(receipt.subtotal || 0)}`;
    if (receiptDiscount) receiptDiscount.textContent = `₦ ${formatCurrency(receipt.discount || 0)}`;
    if (receiptTotal) receiptTotal.textContent = `₦ ${formatCurrency(receipt.total || 0)}`;
    if (receiptPayment) receiptPayment.textContent = receipt.payment || 'Cash';
    if (receiptChange) receiptChange.textContent = `₦ ${formatCurrency(receipt.change || 0)}`;
});

function formatCurrency(value) {
    return Number(value).toLocaleString('en-NG');
}
