/**
 * MADAM HY - Payment detail interactions.
 * Connects to live payment record data and provides interactive controls.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Payment detail is rendered cleanly and dynamically server-side via Django template tags.
    // If any client-side dynamic enhancements or copy-to-clipboard are added, attach here.
    const orderRefEl = document.getElementById('detailOrderRef');
    if (orderRefEl && orderRefEl.textContent.trim() !== '-') {
        orderRefEl.style.cursor = 'pointer';
        orderRefEl.title = 'Click to copy reference';
        orderRefEl.addEventListener('click', () => {
            navigator.clipboard.writeText(orderRefEl.textContent.trim()).then(() => {
                const orig = orderRefEl.textContent;
                orderRefEl.textContent = 'Copied!';
                setTimeout(() => { orderRefEl.textContent = orig; }, 1500);
            });
        });
    }
});
