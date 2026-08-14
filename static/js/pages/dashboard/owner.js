/**
 * MADAM HY - Owner dashboard interactions.
 * Frontend-only demo data for Phase 2.
 */

document.addEventListener("DOMContentLoaded", () => {
    setCurrentDate();
    renderOwnerDashboard();
    setupSalesPeriod();
    setupPlaceholderActions();
});

const ownerDashboardData = {
    metrics: {
        todaySales: 428500,
        todayProfit: 96500,
        monthlySales: 7842500,
        outstandingCredit: 612000,
        salesChange: "+12%",
        profitChange: "+8%",
        monthlySalesChange: "+18%"
    },
    sales: {
        7: [42, 58, 46, 72, 64, 88, 79],
        30: [55, 62, 70, 66, 82, 91, 86],
        90: [48, 64, 73, 81, 76, 92, 89],
        365: [35, 46, 58, 63, 71, 84, 90]
    },
    recentSales: [
        ["Walk-in customer", "NGN 42,500", "Cash", "Today", "Paid"],
        ["Amina Yusuf", "NGN 88,000", "Transfer", "Today", "Paid"],
        ["Grace Retail", "NGN 31,500", "Credit", "Today", "Pending"]
    ],
    lowStock: [
        ["Green Ankara Fabric", "Fabric", 4],
        ["Ladies Sandals", "Footwear", 3],
        ["Kids School Bag", "Bags", 5]
    ],
    credits: [
        ["Amina Yusuf", "NGN 120,000", "Due this week"],
        ["Grace Retail", "NGN 82,500", "Part payment"],
        ["Walk-in account", "NGN 45,000", "Follow up"]
    ],
    requests: [
        ["Silk scarf", "2 customers", "Sourcing"],
        ["Size 42 heels", "1 customer", "Pending"],
        ["Travel luggage", "3 customers", "Review"]
    ],
    growth: {
        salesGrowth: "+18%",
        profitGrowth: "+11%",
        customerGrowth: "+24",
        orderGrowth: "+36"
    }
};

function setCurrentDate() {
    const dateElement = document.getElementById("currentDate");

    if (!dateElement) return;

    dateElement.textContent =
        new Date().toLocaleDateString("en-NG", {
            weekday: "short",
            day: "numeric",
            month: "short",
            year: "numeric"
        });
}

function renderOwnerDashboard() {
    setText("todaySales", formatNumber(ownerDashboardData.metrics.todaySales));
    setText("todayProfit", formatNumber(ownerDashboardData.metrics.todayProfit));
    setText("monthlySales", formatNumber(ownerDashboardData.metrics.monthlySales));
    setText("outstandingCredit", formatNumber(ownerDashboardData.metrics.outstandingCredit));
    setText("salesChange", ownerDashboardData.metrics.salesChange);
    setText("profitChange", ownerDashboardData.metrics.profitChange);
    setText("monthlySalesChange", ownerDashboardData.metrics.monthlySalesChange);

    renderSalesChart("7");
    renderRecentSales();
    renderLowStock();
    renderCredits();
    renderRequests();
    renderGrowth();
}

function setupSalesPeriod() {
    const periodSelect = document.getElementById("salesPeriod");

    if (!periodSelect) return;

    periodSelect.addEventListener("change", event => {
        renderSalesChart(event.target.value);
    });
}

function setupPlaceholderActions() {
    const actions = document.querySelectorAll(".quick-action, .view-all-link");

    actions.forEach(action => {
        action.addEventListener("click", event => {
            event.preventDefault();
            action.blur();
        });
    });
}

function renderSalesChart(period) {
    const chart = document.getElementById("salesChart");
    const values = ownerDashboardData.sales[period] || ownerDashboardData.sales[7];

    if (!chart) return;

    if (!values.length) {
        chart.innerHTML = getEmptyState("No sales data for this period.");
        return;
    }

    const max = Math.max(...values);

    chart.innerHTML = values.map((value, index) => {
        const height = Math.max(18, Math.round((value / max) * 100));

        return `
            <span class="chart-bar" style="--bar-height: ${height}%">
                <i></i>
                <small>Day ${index + 1}</small>
            </span>
        `;
    }).join("");
}

function renderRecentSales() {
    const table = document.getElementById("recentSalesTable");

    if (!table) return;

    if (!ownerDashboardData.recentSales.length) {
        table.innerHTML = `
            <tr>
                <td colspan="5">${getEmptyState("No recent sales yet.")}</td>
            </tr>
        `;
        return;
    }

    table.innerHTML = ownerDashboardData.recentSales.map(row => `
        <tr>
            <td data-label="Customer"><strong>${row[0]}</strong></td>
            <td data-label="Amount">${row[1]}</td>
            <td data-label="Payment">${row[2]}</td>
            <td data-label="Date">${row[3]}</td>
            <td data-label="Status">
                <span class="status-badge ${row[4] === "Paid" ? "status-success" : "status-warning"}">
                    ${row[4]}
                </span>
            </td>
        </tr>
    `).join("");
}

function renderLowStock() {
    const list = document.getElementById("lowStockList");

    if (!list) return;

    if (!ownerDashboardData.lowStock.length) {
        list.innerHTML = getEmptyState("No low-stock products right now.");
        return;
    }

    list.innerHTML = ownerDashboardData.lowStock.map(item => `
        <div class="dashboard-list-item">
            <span class="dashboard-item-icon">${item[0].slice(0, 2).toUpperCase()}</span>
            <span>
                <strong>${item[0]}</strong>
                <small>${item[1]}</small>
            </span>
            <em>${item[2]} left</em>
        </div>
    `).join("");
}

function renderCredits() {
    const list = document.getElementById("creditList");

    if (!list) return;

    if (!ownerDashboardData.credits.length) {
        list.innerHTML = getEmptyState("No outstanding credits to show.");
        return;
    }

    list.innerHTML = ownerDashboardData.credits.map(item => `
        <div class="dashboard-list-item">
            <span>
                <strong>${item[0]}</strong>
                <small>${item[2]}</small>
            </span>
            <em>${item[1]}</em>
        </div>
    `).join("");
}

function renderRequests() {
    const list = document.getElementById("requestList");

    if (!list) return;

    if (!ownerDashboardData.requests.length) {
        list.innerHTML = getEmptyState("No product requests waiting.");
        return;
    }

    list.innerHTML = ownerDashboardData.requests.map(item => `
        <div class="dashboard-list-item">
            <span>
                <strong>${item[0]}</strong>
                <small>${item[1]}</small>
            </span>
            <em>${item[2]}</em>
        </div>
    `).join("");
}

function renderGrowth() {
    Object.entries(ownerDashboardData.growth).forEach(([id, value]) => {
        setText(id, value);
    });
}

function setText(id, value) {
    const element = document.getElementById(id);

    if (element) {
        element.textContent = value;
    }
}

function getEmptyState(message) {
    return `
        <div class="empty-state dashboard-empty-state">
            <h3>${message}</h3>
            <p>Demo data can be replaced when backend integration begins.</p>
        </div>
    `;
}

function formatNumber(value) {
    return new Intl.NumberFormat("en-NG", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(Number(value) || 0);
}
