const requestDetailData = {
    id: 'REQ-1003',
    customer: 'Grace Nnaji',
    type: 'Inventory Issue',
    title: 'Missing stock count for beverages',
    description: 'Warehouse count for packaged drinks does not match the current shelf stock and needs verification. The request is urgent because the display shelves are running low and early confirmation is needed to avoid a stock gap.',
    notes: 'The store manager has requested a physical count and shelf check before the next delivery window. The request should be reviewed by inventory staff before 4pm.',
    priority: 'Urgent',
    status: 'Approved',
    assignee: 'Samuel Eze',
    created: '2026-08-10T12:40:00',
    updated: '2026-08-14T08:15:00',
    timeline: [
        { title: 'Request submitted', text: 'Submitted by Grace Nnaji on 10 Aug 2026.', date: '2026-08-10T12:40:00' },
        { title: 'Inventory review', text: 'Warehouse team started checking shelf counts and stock records.', date: '2026-08-11T09:00:00' },
        { title: 'Approved', text: 'Request approved and assigned to Samuel Eze for action.', date: '2026-08-14T08:15:00' }
    ]
};

document.addEventListener('DOMContentLoaded', () => {
    renderDetail();
    bindActions();
});

function renderDetail() {
    document.getElementById('detailTitle')?.replaceChildren(document.createTextNode(requestDetailData.title));
    document.getElementById('detailSubtitle')?.replaceChildren(document.createTextNode(`${requestDetailData.customer} • ${requestDetailData.type}`));
    document.getElementById('detailReference')?.replaceChildren(document.createTextNode(requestDetailData.id));
    document.getElementById('detailPriority')?.replaceChildren(document.createTextNode(requestDetailData.priority));
    document.getElementById('detailStatus')?.replaceChildren(document.createTextNode(requestDetailData.status));
    document.getElementById('detailAssignee')?.replaceChildren(document.createTextNode(requestDetailData.assignee));
    document.getElementById('detailCustomer')?.replaceChildren(document.createTextNode(requestDetailData.customer));
    document.getElementById('detailType')?.replaceChildren(document.createTextNode(requestDetailData.type));
    document.getElementById('detailCreated')?.replaceChildren(document.createTextNode(formatDate(requestDetailData.created)));
    document.getElementById('detailUpdated')?.replaceChildren(document.createTextNode(formatDate(requestDetailData.updated)));
    document.getElementById('detailDescription')?.replaceChildren(document.createTextNode(requestDetailData.description));
    document.getElementById('detailNotes')?.replaceChildren(document.createTextNode(requestDetailData.notes));

    const timeline = document.getElementById('detailTimeline');
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

function bindActions() {
    document.getElementById('requestActionReview')?.addEventListener('click', () => {
        const status = document.getElementById('detailStatus');
        if (status) {
            status.textContent = 'In Review';
            status.classList.add('request-status-in-review');
        }
    });

    document.getElementById('requestActionApprove')?.addEventListener('click', () => {
        const status = document.getElementById('detailStatus');
        if (status) {
            status.textContent = 'Approved';
            status.classList.add('request-status-approved');
        }
    });
}

function formatDate(value) {
    return new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}
