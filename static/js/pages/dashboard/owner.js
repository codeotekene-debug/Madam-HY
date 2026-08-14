/**
 * =========================================================
 * MADAM HY — OWNER DASHBOARD
 * Page JavaScript
 * =========================================================
 */

document.addEventListener("DOMContentLoaded", () => {

    initializeDashboard();

});


/**
 * =========================================================
 * INITIALIZE DASHBOARD
 * =========================================================
 */

function initializeDashboard() {

    setDashboardDate();

    setupSalesPeriod();

    setupDashboardInteractions();

}


/**
 * =========================================================
 * DASHBOARD DATE
 * =========================================================
 */

function setDashboardDate() {

    const dateElement =
        document.getElementById("dashboardDate");

    if (!dateElement) {
        return;
    }

    const today = new Date();

    const options = {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric"
    };

    dateElement.textContent =
        today.toLocaleDateString("en-NG", options);

}


/**
 * =========================================================
 * SALES PERIOD
 * =========================================================
 */

function setupSalesPeriod() {

    const periodSelect =
        document.getElementById("salesPeriod");

    if (!periodSelect) {
        return;
    }

    periodSelect.addEventListener("change", function () {

        const selectedPeriod = this.value;

        handleSalesPeriodChange(selectedPeriod);

    });

}


/**
 * =========================================================
 * SALES PERIOD CHANGE
 * =========================================================
 */

function handleSalesPeriodChange(period) {

    console.log(
        "Sales period changed:",
        period
    );

    /*
     * AJAX will be connected here.
     *
     * Example:
     *
     * loadSalesChart(period);
     */

}


/**
 * =========================================================
 * DASHBOARD INTERACTIONS
 * =========================================================
 */

function setupDashboardInteractions() {

    setupQuickActions();

    setupAlertItems();

}


/**
 * =========================================================
 * QUICK ACTIONS
 * =========================================================
 */

function setupQuickActions() {

    const quickActions =
        document.querySelectorAll(".quick-action");

    quickActions.forEach(action => {

        action.addEventListener("click", function () {

            /*
             * Navigation will be handled by Django URLs.
             *
             * We are intentionally not hard-coding
             * URLs here yet.
             */

        });

    });

}


/**
 * =========================================================
 * BUSINESS ALERTS
 * =========================================================
 */

function setupAlertItems() {

    const alerts =
        document.querySelectorAll(".alert-item");

    alerts.forEach(alert => {

        alert.addEventListener("click", function () {

            /*
             * Django URL navigation will be connected later.
             */

        });

    });

}


/**
 * =========================================================
 * CURRENCY FORMATTER
 * =========================================================
 */

function formatCurrency(amount) {

    const value =
        Number(amount) || 0;

    return new Intl.NumberFormat(
        "en-NG",
        {
            style: "currency",
            currency: "NGN",
            minimumFractionDigits: 2
        }
    ).format(value);

}


/**
 * =========================================================
 * NUMBER FORMATTER
 * =========================================================
 */

function formatNumber(number) {

    return new Intl.NumberFormat(
        "en-NG"
    ).format(
        Number(number) || 0
    );

}


/**
 * =========================================================
 * UPDATE DASHBOARD VALUE
 * =========================================================
 */

function updateDashboardValue(
    elementId,
    value
) {

    const element =
        document.getElementById(elementId);

    if (!element) {
        return;
    }

    element.textContent =
        formatCurrency(value);

}


/**
 * =========================================================
 * UPDATE DASHBOARD NUMBER
 * =========================================================
 */

function updateDashboardNumber(
    elementId,
    value
) {

    const element =
        document.getElementById(elementId);

    if (!element) {
        return;
    }

    element.textContent =
        formatNumber(value);

}


/**
 * =========================================================
 * UPDATE GROWTH
 * =========================================================
 */

function updateGrowth(
    elementId,
    percentage
) {

    const element =
        document.getElementById(elementId);

    if (!element) {
        return;
    }

    const value =
        Number(percentage) || 0;

    element.textContent =
        `${value.toFixed(1)}%`;

}


/**
 * =========================================================
 * LOADING STATE
 * =========================================================
 */

function setDashboardLoading(
    loading = true
) {

    const loadingElements =
        document.querySelectorAll(
            "[data-dashboard-loading]"
        );

    loadingElements.forEach(element => {

        element.classList.toggle(
            "is-loading",
            loading
        );

    });

}


/**
 * =========================================================
 * EMPTY STATE
 * =========================================================
 */

function showEmptyState(
    containerId,
    message
) {

    const container =
        document.getElementById(containerId);

    if (!container) {
        return;
    }

    container.innerHTML = `
        <div class="dashboard-empty-state">
            <span>${message}</span>
        </div>
    `;

}


/**
 * =========================================================
 * ERROR MESSAGE
 * =========================================================
 */

function showDashboardError(
    message
) {

    console.error(
        "Dashboard Error:",
        message
    );

}


/**
 * =========================================================
 * EXPORT FUNCTIONS
 * =========================================================
 *
 * These functions can be used by owner.ajax.js
 */

window.MadamHYDashboard = {

    formatCurrency,

    formatNumber,

    updateDashboardValue,

    updateDashboardNumber,

    updateGrowth,

    setDashboardLoading,

    showEmptyState,

    showDashboardError

};