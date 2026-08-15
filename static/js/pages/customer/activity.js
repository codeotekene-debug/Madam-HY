/**
 * MADAM HY - Customer Activity
 * Frontend-only customer activity timeline
 */

const activityData = [
    { title: 'Order placed', text: 'You placed order ORD-2026-0847', date: '2026-08-12T10:30:00', type: 'Order' },
    { title: 'Order delivered', text: 'Order ORD-2026-0846 was delivered', date: '2026-08-10T14:15:00', type: 'Order' },
    { title: 'Credit payment', text: 'You made a credit payment of ₦5,000', date: '2026-08-08T09:00:00', type: 'Payment' },
    { title: 'Request approved', text: 'Your product request REQ-1501 was approved', date: '2026-08-06T16:30:00', type: 'Request' },
    { title: 'Profile updated', text: 'You updated your account information', date: '2026-08-01T11:20:00', type: 'Profile update' },
    { title: 'Order placed', text: 'You placed order ORD-2026-0844', date: '2026-07-28T08:45:00', type: 'Order' }
];

document.addEventListener('DOMContentLoaded', () => {
    setupFilters();
    renderActivity();
});

function setupFilters() {
    const search = document.getElementById('activitySearch');
    const type = document.getElementById('activityTypeFilter');

    const applyFilters = () => renderActivity();
    search?.addEventListener('input', applyFilters);
    type?.addEventListener('change', applyFilters);
}

function renderActivity() {
    const list = document.getElementById('activityList');
    const empty = document.getElementById('activityEmpty');

    if (!list) return;

    const searchValue = document.getElementById('activitySearch')?.value.toLowerCase() || '';
    const typeFilter = document.getElementById('activityTypeFilter')?.value || 'all';

    let filtered = activityData.filter(item => {
        const matchesSearch = !searchValue || item.text.toLowerCase().includes(searchValue);
        const matchesType = typeFilter === 'all' || item.type === typeFilter;
        return matchesSearch && matchesType;
    });

    if (!filtered.length) {
        list.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        return;
    }

    empty?.classList.add('empty-state-hidden');
    list.innerHTML = filtered.map(item => `
        <div class="timeline-item">
            <strong>${item.title}</strong>
            <span>${item.text}</span>
            <span>${formatDate(item.date)}</span>
        </div>
    `).join('');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
