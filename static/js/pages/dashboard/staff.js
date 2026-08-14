/**
 * MADAM HY - Staff dashboard interactions.
 * Frontend-only operational demo data for Phase 2.
 */

document.addEventListener("DOMContentLoaded", () => {
    setStaffDate();
    renderStaffDashboard();
    setupTaskFilter();
    setupStaffActions();
});

const staffDashboardData = {
    metrics: {
        openTasks: 8,
        ordersToPrepare: 5,
        stockChecks: 3,
        requestsToReview: 4
    },
    tasks: [
        {
            title: "Confirm transfer payment for pickup order",
            detail: "Order #MH-2048 needs payment confirmation before release.",
            type: "orders",
            priority: true,
            status: "Priority"
        },
        {
            title: "Check shelf count for Green Ankara Fabric",
            detail: "Displayed quantity is low; confirm before restock request.",
            type: "stock",
            priority: false,
            status: "Stock"
        },
        {
            title: "Review customer request for size 42 heels",
            detail: "Confirm style and color preference before market sourcing.",
            type: "requests",
            priority: true,
            status: "Request"
        },
        {
            title: "Prepare two packed orders for afternoon pickup",
            detail: "Keep receipts with the packages at the front desk.",
            type: "orders",
            priority: false,
            status: "Orders"
        }
    ],
    orders: [
        ["#MH-2048", "Amina Yusuf", "Confirm payment", "Pending"],
        ["#MH-2049", "Walk-in customer", "Pack items", "Ready"],
        ["#MH-2050", "Grace Retail", "Prepare pickup", "Pending"]
    ],
    notes: [
        ["Morning handover", "Check requested sandals before 2 PM."],
        ["Stock room", "Keep new bags aside until count is confirmed."],
        ["Customer follow-up", "Call Grace Retail after transfer confirmation."]
    ]
};

function setStaffDate() {
    const dateElement = document.getElementById("staffShiftDate");

    if (!dateElement) return;

    dateElement.textContent =
        new Date().toLocaleDateString("en-NG", {
            weekday: "short",
            day: "numeric",
            month: "short"
        });
}

function renderStaffDashboard(filter = "all") {
    Object.entries(staffDashboardData.metrics).forEach(([id, value]) => {
        setText(id, value);
    });

    renderTasks(filter);
    renderOrders();
    renderNotes();
}

function setupTaskFilter() {
    const filter = document.getElementById("taskFilter");

    if (!filter) return;

    filter.addEventListener("change", event => {
        renderTasks(event.target.value);
    });
}

function setupStaffActions() {
    const actions = document.querySelectorAll("[data-staff-action]");

    actions.forEach(action => {
        action.addEventListener("click", () => {
            showStaffMessage(
                "This action is ready for Django URL and permission integration."
            );
        });
    });
}

function renderTasks(filter) {
    const list = document.getElementById("staffTaskList");

    if (!list) return;

    const tasks = staffDashboardData.tasks.filter(task => {
        if (filter === "all") return true;
        if (filter === "priority") return task.priority;

        return task.type === filter;
    });

    if (!tasks.length) {
        list.innerHTML = `
            <div class="empty-state">
                <h3>No tasks found</h3>
                <p>Try another operational filter.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = tasks.map(task => `
        <div class="staff-task">
            <span>
                <strong>${task.title}</strong>
                <small>${task.detail}</small>
            </span>
            <em>${task.status}</em>
        </div>
    `).join("");
}

function renderOrders() {
    const table = document.getElementById("staffOrdersTable");

    if (!table) return;

    if (!staffDashboardData.orders.length) {
        table.innerHTML = `
            <tr>
                <td colspan="4">
                    <div class="empty-state staff-empty-state">
                        <h3>No orders need attention</h3>
                        <p>The operational queue is clear.</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = staffDashboardData.orders.map(order => `
        <tr>
            <td data-label="Order"><strong>${order[0]}</strong></td>
            <td data-label="Customer">${order[1]}</td>
            <td data-label="Work">${order[2]}</td>
            <td data-label="Status">
                <span class="status-badge ${order[3] === "Ready" ? "status-ready" : "status-pending"}">
                    ${order[3]}
                </span>
            </td>
        </tr>
    `).join("");
}

function renderNotes() {
    const list = document.getElementById("handoverList");

    if (!list) return;

    if (!staffDashboardData.notes.length) {
        list.innerHTML = `
            <div class="empty-state staff-empty-state">
                <h3>No handover notes</h3>
                <p>Shift notes will appear here during backend integration.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = staffDashboardData.notes.map(note => `
        <div class="staff-note">
            <strong>${note[0]}</strong>
            <small>${note[1]}</small>
        </div>
    `).join("");
}

function showStaffMessage(message) {
    const messageBox = document.getElementById("staffMessage");

    if (!messageBox) return;

    messageBox.hidden = false;
    messageBox.textContent = message;
}

function setText(id, value) {
    const element = document.getElementById(id);

    if (element) {
        element.textContent = value;
    }
}
