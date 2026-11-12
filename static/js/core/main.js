/**
 * MADAM HY shared frontend bootstrap.
 *
 * Keep feature-specific shell behavior in focused core files.
 * Example: sidebar and mobile menu behavior lives in navigation.js.
 */

window.updateCustomerCartBadge = function(count) {
    const badge = document.getElementById('topbarCartBadge');
    if (!badge) return;
    if (typeof count === 'number') {
        badge.textContent = String(count);
        badge.classList.toggle('has-items', count > 0);
        return;
    }
    if (window.apiRequest) {
        window.apiRequest('/customer/cart/?format=json').then(res => {
            if (res && res.success && res.data) {
                const total = res.data.item_count || 0;
                badge.textContent = String(total);
                badge.classList.toggle('has-items', total > 0);
            }
        }).catch(() => {});
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const appContext = document.getElementById('app-context');
    if (appContext && appContext.dataset.authenticated === 'true') {
        window.updateCustomerCartBadge();
    }
    enhanceScrollableTables();
    const content = document.getElementById('main-content') || document.getElementById('customer-main-content');
    if (content && window.MutationObserver) {
        const tableObserver = new MutationObserver(() => window.requestAnimationFrame(enhanceScrollableTables));
        tableObserver.observe(content, { childList: true, subtree: true });
    }
});

function enhanceScrollableTables() {
    document.querySelectorAll('.table-wrapper, .table-responsive').forEach(wrapper => {
        const overflows = wrapper.scrollWidth > wrapper.clientWidth + 1;
        wrapper.classList.toggle('has-horizontal-overflow', overflows);
        if (!overflows) return;

        if (!wrapper.hasAttribute('tabindex')) wrapper.tabIndex = 0;
        if (!wrapper.hasAttribute('role')) wrapper.setAttribute('role', 'region');
        if (!wrapper.hasAttribute('aria-label') && !wrapper.hasAttribute('aria-labelledby')) {
            const caption = wrapper.querySelector('caption')?.textContent.trim();
            const heading = wrapper.closest('section, article')?.querySelector('h2, h3')?.textContent.trim();
            wrapper.setAttribute('aria-label', caption || (heading ? `${heading} table` : 'Scrollable data table'));
        }
    });
}

window.addEventListener('page:load', enhanceScrollableTables);
window.addEventListener('resize', enhanceScrollableTables, { passive: true });
