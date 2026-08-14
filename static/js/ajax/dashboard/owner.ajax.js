/**
 * =========================================================
 * MADAM HY — OWNER DASHBOARD AJAX
 * =========================================================
 *
 * This file handles communication between the dashboard
 * and Django.
 *
 * IMPORTANT:
 * Database/API endpoints will be connected later.
 * =========================================================
 */


document.addEventListener("DOMContentLoaded", () => {

    loadDashboardData();

});


/**
 * =========================================================
 * MAIN DASHBOARD REQUEST
 * =========================================================
 */

async function loadDashboardData() {

    try {

        setAjaxLoading(true);

        /*
         * We will connect this to a Django URL later.
         *
         * Example:
         *
         * const response = await fetch(
         *     "/dashboard/api/summary/"
         * );
         *
         * const data = await response.json();
         *
         * updateDashboard(data);
         */

        console.log(
            "Dashboard AJAX initialized."
        );

    } catch (error) {

        console.error(
            "Unable to load dashboard data:",
            error
        );

        handleAjaxError(error);

    } finally {

        setAjaxLoading(false);

    }

}


/**
 * =========================================================
 * LOAD SALES DATA
 * =========================================================
 */

async function loadSalesData(period = 7) {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     `/dashboard/api/sales/?period=${period}`
         * );
         *
         * const data = await response.json();
         *
         * updateSalesChart(data);
         */

        console.log(
            `Loading sales for ${period} days`
        );

    } catch (error) {

        console.error(
            "Sales AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD LOW STOCK PRODUCTS
 * =========================================================
 */

async function loadLowStockProducts() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/dashboard/api/low-stock/"
         * );
         *
         * const data = await response.json();
         *
         * updateLowStockProducts(data);
         */

        console.log(
            "Loading low stock products..."
        );

    } catch (error) {

        console.error(
            "Low stock AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD RECENT SALES
 * =========================================================
 */

async function loadRecentSales() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/dashboard/api/recent-sales/"
         * );
         *
         * const data = await response.json();
         *
         * updateRecentSales(data);
         */

        console.log(
            "Loading recent sales..."
        );

    } catch (error) {

        console.error(
            "Recent sales AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD TOP PRODUCTS
 * =========================================================
 */

async function loadTopProducts() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/dashboard/api/top-products/"
         * );
         *
         * const data = await response.json();
         *
         * updateTopProducts(data);
         */

        console.log(
            "Loading top products..."
        );

    } catch (error) {

        console.error(
            "Top products AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD BUSINESS GROWTH
 * =========================================================
 */

async function loadBusinessGrowth() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/dashboard/api/growth/"
         * );
         *
         * const data = await response.json();
         *
         * updateBusinessGrowth(data);
         */

        console.log(
            "Loading business growth..."
        );

    } catch (error) {

        console.error(
            "Business growth AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD CUSTOMER CREDITS
 * =========================================================
 */

async function loadCustomerCredits() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/credits/api/outstanding/"
         * );
         *
         * const data = await response.json();
         *
         * updateCreditSummary(data);
         */

        console.log(
            "Loading customer credits..."
        );

    } catch (error) {

        console.error(
            "Credits AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * LOAD PRODUCT REQUESTS
 * =========================================================
 */

async function loadProductRequests() {

    try {

        /*
         * Later:
         *
         * const response = await fetch(
         *     "/requests/api/pending/"
         * );
         *
         * const data = await response.json();
         *
         * updateProductRequests(data);
         */

        console.log(
            "Loading product requests..."
        );

    } catch (error) {

        console.error(
            "Product request AJAX error:",
            error
        );

    }

}


/**
 * =========================================================
 * UPDATE DASHBOARD
 * =========================================================
 */

function updateDashboard(data) {

    if (!data) {
        return;
    }


    /*
     * Today's sales
     */

    if (data.today_sales !== undefined) {

        MadamHYDashboard.updateDashboardValue(
            "todaySales",
            data.today_sales
        );

    }


    /*
     * Today's profit
     */

    if (data.today_profit !== undefined) {

        MadamHYDashboard.updateDashboardValue(
            "todayProfit",
            data.today_profit
        );

    }


    /*
     * Today's expenses
     */

    if (data.today_expenses !== undefined) {

        MadamHYDashboard.updateDashboardValue(
            "todayExpenses",
            data.today_expenses
        );

    }


    /*
     * Outstanding customer credit
     */

    if (data.outstanding_credit !== undefined) {

        MadamHYDashboard.updateDashboardValue(
            "outstandingCredit",
            data.outstanding_credit
        );

    }


    /*
     * Total customers
     */

    if (data.total_customers !== undefined) {

        MadamHYDashboard.updateDashboardNumber(
            "totalCustomers",
            data.total_customers
        );

    }


    /*
     * Total products
     */

    if (data.total_products !== undefined) {

        MadamHYDashboard.updateDashboardNumber(
            "totalProducts",
            data.total_products
        );

    }

}


/**
 * =========================================================
 * AJAX LOADING STATE
 * =========================================================
 */

function setAjaxLoading(
    loading = true
) {

    if (
        window.MadamHYDashboard &&
        MadamHYDashboard.setDashboardLoading
    ) {

        MadamHYDashboard.setDashboardLoading(
            loading
        );

    }

}


/**
 * =========================================================
 * AJAX ERROR HANDLER
 * =========================================================
 */

function handleAjaxError(error) {

    console.error(
        "MADAM HY Dashboard AJAX Error:",
        error
    );

}


/**
 * =========================================================
 * SALES PERIOD LISTENER
 * =========================================================
 */

document.addEventListener(
    "change",
    event => {

        if (
            event.target.id !== "salesPeriod"
        ) {
            return;
        }


        const period =
            event.target.value;


        loadSalesData(period);

    }
);


/**
 * =========================================================
 * EXPORT AJAX FUNCTIONS
 * =========================================================
 */

window.MadamHYDashboardAjax = {

    loadDashboardData,

    loadSalesData,

    loadLowStockProducts,

    loadRecentSales,

    loadTopProducts,

    loadBusinessGrowth,

    loadCustomerCredits,

    loadProductRequests

};