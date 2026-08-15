/**
 * MADAM HY - Customer Requests
 * Frontend-only customer request management
 */

const customerRequestsData = [
    {
        id: 'REQ-1501',
        title: 'Request for imported fabric stock',
        type: 'Product Request',
        status: 'Approved',
        created: '2026-08-10T08:30:00',
        updated: '2026-08-12T14:00:00'
    },
    {
        id: 'REQ-1500',
        title: 'Delivery delay inquiry',
        type: 'Order Follow-up',
        status: 'Pending',
        created: '2026-08-08T10:15:00',
        updated: '2026-08-08T10:15:00'
    },
    {
        id: 'REQ-1499',
        title: 'Special order customization',
        type: 'Product Request',
        status: 'In Review',
        created: '2026-08-05T09:00:00',
        updated: '2026-08-06T16:30:00'
    }
];

const requestDetailData = {
    id: 'REQ-1501',
    title: 'Request for imported fabric stock',
    type: 'Product Request',
    status: 'Approved',
    created: '2026-08-10T08:30:00',
    updated: '2026-08-12T14:00:00',
    description: 'I am interested in purchasing imported Ankara fabric stock for retail. Please provide information on availability and bulk pricing.',
    notes: 'Request approved. Stock will be available by next month.',
    timeline: [
        { title: 'Request submitted', text: 'Your request was successfully submitted', date: '2026-08-10T08:30:00' },
        { title: 'Request received', text: 'Shop team has received and reviewed your request', date: '2026-08-11T09:00:00' },
        { title: 'Approved', text: 'Your request has been approved and is being processed', date: '2026-08-12T14:00:00' }
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    const isDetail = window.location.pathname.includes('/request_detail/');
    if (isDetail) {
        renderRequestDetail();
    } else {
        renderRequestsList();
    }
});

function renderRequestsList() {
    renderSummary();
    bindFilters();
    renderTable();
}

function renderSummary() {
    const total = customerRequestsData.length;
    const pending = customerRequestsData.filter(item => item.status === 'Pending').length;
    const completed = customerRequestsData.filter(item => item.status === 'Approved' || item.status === 'Completed').length;

    document.getElementById('customerTotalRequests')?.replaceChildren(document.createTextNode(String(total)));
    document.getElementById('customerPendingRequests')?.replaceChildren(document.createTextNode(String(pending)));
    document.getElementById('customerCompletedRequests')?.replaceChildren(document.createTextNode(String(completed)));
}

function bindFilters() {
    const search = document.getElementById('customerRequestsSearch');
    const status = document.getElementById('customerRequestsStatusFilter');

    const applyFilters = () => renderTable();
    search?.addEventListener('input', applyFilters);
    status?.addEventListener('change', applyFilters);
}

function renderTable() {
    const tableBody = document.getElementById('customerRequestsTableBody');
    const empty = document.getElementById('customerRequestsEmpty');

    if (!tableBody) return;

    const searchValue = document.getElementById('customerRequestsSearch')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('customerRequestsStatusFilter')?.value || 'all';

    let filtered = customerRequestsData.filter(item => {
        const matchesSearch = !searchValue || item.id.toLowerCase().includes(searchValue) || item.title.toLowerCase().includes(searchValue);
        const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
        return matchesSearch && matchesStatus;
    });

    if (!filtered.length) {
        tableBody.innerHTML = '';
        empty?.classList.remove('empty-state-hidden');
        return;
    }

    empty?.classList.add('empty-state-hidden');
    tableBody.innerHTML = filtered.map(item => `
        <tr>
            <td><strong>${item.id}</strong></td>
            <td>${item.title}</td>
            <td>${item.type}</td>
            <td><span class="request-status ${item.status.toLowerCase().replace(/\s+/g, '-')}">${item.status}</span></td>
            <td>${formatDate(item.created)}</td>
            <td><a href="/customer/request/${item.id}/" class="request-action-link">View</a></td>
        </tr>
    `).join('');
}

function renderRequestDetail() {
    document.getElementById('detailReqTitle')?.replaceChildren(document.createTextNode(requestDetailData.title));
    document.getElementById('detailReqStatus')?.replaceChildren(document.createTextNode(requestDetailData.status));
    document.getElementById('detailReqSubtitle')?.replaceChildren(document.createTextNode(`${requestDetailData.type} • ${requestDetailData.status}`));

    document.getElementById('detailReqReference')?.replaceChildren(document.createTextNode(requestDetailData.id));
    document.getElementById('detailReqType')?.replaceChildren(document.createTextNode(requestDetailData.type));
    document.getElementById('detailReqCreated')?.replaceChildren(document.createTextNode(formatDate(requestDetailData.created)));
    document.getElementById('detailReqUpdated')?.replaceChildren(document.createTextNode(formatDate(requestDetailData.updated)));
    document.getElementById('detailReqDescription')?.replaceChildren(document.createTextNode(requestDetailData.description));
    document.getElementById('detailReqNotes')?.replaceChildren(document.createTextNode(requestDetailData.notes));

    const timeline = document.getElementById('detailReqTimeline');
    if (timeline) {
        timeline.innerHTML = requestDetailData.timeline.map(item => `
            <div class="timeline-item">
                <strong>${item.title}</strong>
                <span>${item.text}</span>
                <span>${formatDate(item.date)}</span>
            </div>
        `).join('');
    }
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
