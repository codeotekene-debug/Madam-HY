const requestsData = [
    {
        id: 'REQ-1001',
        customer: 'Aisha Bello',
        type: 'Product Request',
        title: 'Request for baby food stock',
        description: 'Customer wants a reliable restock of baby food products and would like delivery follow-up after approval.',
        priority: 'High',
        status: 'Pending',
        assignee: 'Mary James',
        created: '2026-08-12T08:30:00',
        updated: '2026-08-13T14:00:00'
    },
    {
        id: 'REQ-1002',
        customer: 'Musa Adamu',
        type: 'Customer Support',
        title: 'Issue with order delivery update',
        description: 'Customer reported that delivery status has not been updated for the last few hours and is waiting for the next step.',
        priority: 'Medium',
        status: 'In Review',
        assignee: 'John Okafor',
        created: '2026-08-11T09:10:00',
        updated: '2026-08-14T10:10:00'
    },
    {
        id: 'REQ-1003',
        customer: 'Grace Nnaji',
        type: 'Inventory Issue',
        title: 'Missing stock count for beverages',
        description: 'Warehouse count for packaged drinks does not match the current shelf stock and needs verification.',
        priority: 'Urgent',
        status: 'Approved',
        assignee: 'Samuel Eze',
        created: '2026-08-10T12:40:00',
        updated: '2026-08-14T08:15:00'
    },
    {
        id: 'REQ-1004',
        customer: 'Emeka Ibe',
        type: 'Payment Concern',
        title: 'Transfer payment confirmation request',
        description: 'Customer needs confirmation that the transferred payment has been received and reconciled correctly.',
        priority: 'Low',
        status: 'Completed',
        assignee: 'Mercy Longe',
        created: '2026-08-08T15:20:00',
        updated: '2026-08-14T07:50:00'
    },
    {
        id: 'REQ-1005',
        customer: 'Sade Okon',
        type: 'Order Follow-up',
        title: 'Replacement request for damaged parcel',
        description: 'Customer requested a replacement item after receiving a damaged package and a follow-up on compensation.',
        priority: 'High',
        status: 'Rejected',
        assignee: 'Mary James',
        created: '2026-08-06T11:00:00',
        updated: '2026-08-12T16:40:00'
    },
    {
        id: 'REQ-1006',
        customer: 'Tunde Babs',
        type: 'Product Request',
        title: 'Request for imported skincare products',
        description: 'Customer asked the shop to source an imported skincare line and share the next estimated restock date.',
        priority: 'Medium',
        status: 'Cancelled',
        assignee: 'Ada Okoye',
        created: '2026-08-05T09:55:00',
        updated: '2026-08-13T13:20:00'
    }
];

document.addEventListener('DOMContentLoaded', () => {
    renderSummary();
    bindFilters();
    renderTable();
    showLoading(false);
});

function bindFilters() {
    const inputs = [
        document.getElementById('requestsSearch'),
        document.getElementById('requestsStatusFilter'),
        document.getElementById('requestsPriorityFilter'),
        document.getElementById('requestsTypeFilter'),
        document.getElementById('requestsSort')
    ];

    inputs.forEach((element) => {
        if (!element) return;
        element.addEventListener('input', renderTable);
        element.addEventListener('change', renderTable);
    });
}

function renderSummary() {
    const total = requestsData.length;
    const pending = requestsData.filter(item => item.status === 'Pending').length;
    const inReview = requestsData.filter(item => item.status === 'In Review').length;
    const urgent = requestsData.filter(item => item.priority === 'Urgent').length;

    document.getElementById('totalRequestsCount')?.replaceChildren(document.createTextNode(String(total)));
    document.getElementById('pendingRequestsCount')?.replaceChildren(document.createTextNode(String(pending)));
    document.getElementById('inReviewRequestsCount')?.replaceChildren(document.createTextNode(String(inReview)));
    document.getElementById('urgentRequestsCount')?.replaceChildren(document.createTextNode(String(urgent)));
}

function renderTable() {
    const tableBody = document.getElementById('requestsTableBody');
    const emptyState = document.getElementById('requestsEmptyState');
    const searchValue = document.getElementById('requestsSearch')?.value.trim().toLowerCase() || '';
    const statusFilter = document.getElementById('requestsStatusFilter')?.value || 'all';
    const priorityFilter = document.getElementById('requestsPriorityFilter')?.value || 'all';
    const typeFilter = document.getElementById('requestsTypeFilter')?.value || 'all';
    const sortValue = document.getElementById('requestsSort')?.value || 'updated-desc';

    if (!tableBody) return;

    let filtered = requestsData.filter((item) => {
        const matchesSearch = !searchValue || [
            item.id,
            item.customer,
            item.title,
            item.type,
            item.assignee
        ].join(' ').toLowerCase().includes(searchValue);

        const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
        const matchesPriority = priorityFilter === 'all' || item.priority === priorityFilter;
        const matchesType = typeFilter === 'all' || item.type === typeFilter;

        return matchesSearch && matchesStatus && matchesPriority && matchesType;
    });

    filtered = filtered.sort((a, b) => {
        if (sortValue === 'updated-asc') return new Date(a.updated) - new Date(b.updated);
        if (sortValue === 'priority-desc') return priorityWeight(b.priority) - priorityWeight(a.priority);
        if (sortValue === 'title-asc') return a.title.localeCompare(b.title);
        return new Date(b.updated) - new Date(a.updated);
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        emptyState?.classList.remove('empty-state-hidden');
        return;
    }

    emptyState?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(item => `
        <tr>
            <td><strong>${item.id}</strong></td>
            <td>${item.customer}</td>
            <td>${item.type}</td>
            <td>${item.title}</td>
            <td><span class="request-priority ${item.priority.toLowerCase()}">${item.priority}</span></td>
            <td><span class="request-status ${slugify(item.status)}">${item.status}</span></td>
            <td>${item.assignee}</td>
            <td>${formatDate(item.updated)}</td>
            <td><a href="/requests/detail/" class="request-action-link">View</a></td>
        </tr>
    `).join('');
}

function showLoading(isLoading) {
    const loadingState = document.getElementById('requestsLoadingState');
    if (!loadingState) return;

    if (isLoading) {
        loadingState.classList.remove('empty-state-hidden');
    } else {
        loadingState.classList.add('empty-state-hidden');
    }
}

function priorityWeight(priority) {
    const map = { Low: 1, Medium: 2, High: 3, Urgent: 4 };
    return map[priority] || 0;
}

function slugify(value) {
    return value.toLowerCase().replace(/\s+/g, '-');
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
