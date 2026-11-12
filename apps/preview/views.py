from django.shortcuts import render


def preview_home(request):
    preview_routes = [
        ("/preview/accounts/login/", "Accounts Login"),
        ("/preview/accounts/register/", "Accounts Register"),
        ("/preview/accounts/forgot-password/", "Accounts Forgot Password"),
        ("/preview/accounts/reset-password/", "Accounts Reset Password"),
        ("/preview/accounts/profile/", "Accounts Profile"),
        ("/preview/dashboard/owner/", "Dashboard Owner"),
        ("/preview/dashboard/staff/", "Dashboard Staff"),
        ("/preview/products/", "Products"),
        ("/preview/products/detail/", "Product Detail"),
        ("/preview/products/add/", "Add Product"),
        ("/preview/products/edit/", "Edit Product"),
        ("/preview/products/categories/", "Product Categories"),
        ("/preview/inventory/", "Inventory"),
        ("/preview/inventory/add/", "Add Stock"),
        ("/preview/inventory/low-stock/", "Low Stock"),
        ("/preview/inventory/history/", "Stock History"),
        ("/preview/sales/pos/", "POS"),
        ("/preview/sales/dashboard/", "Sales Dashboard"),
        ("/preview/sales/checkout/", "Sales Checkout"),
        ("/preview/sales/receipt/", "Sales Receipt"),
        ("/preview/sales/history/", "Sales History"),
        ("/preview/sales/detail/", "Sales Detail"),
        ("/preview/orders/", "Orders"),
        ("/preview/orders/detail/", "Order Detail"),
        ("/preview/payments/", "Payments"),
        ("/preview/payments/detail/", "Payment Detail"),
        ("/preview/payments/success/", "Payment Success"),
        ("/preview/payments/failed/", "Payment Failed"),
        ("/preview/credits/", "Credits"),
        ("/preview/credits/detail/", "Credit Detail"),
        ("/preview/credits/payment/", "Credit Payment"),
        ("/preview/expenses/", "Expenses"),
        ("/preview/expenses/detail/", "Expense Detail"),
        ("/preview/expenses/add/", "Add Expense"),
        ("/preview/reports/", "Reports"),
        ("/preview/reports/sales/", "Sales Report"),
        ("/preview/reports/profit/", "Profit Report"),
        ("/preview/reports/expense/", "Expense Report"),
        ("/preview/reports/growth/", "Growth Report"),
        ("/preview/requests/", "Requests"),
        ("/preview/requests/create/", "Create Request"),
        ("/preview/requests/detail/", "Request Detail"),
        ("/preview/customer/", "Customer Dashboard"),
        ("/preview/customer/products/", "Customer Products"),
        ("/preview/customer/product-detail/", "Customer Product Detail"),
        ("/preview/customer/cart/", "Customer Cart"),
        ("/preview/customer/checkout/", "Customer Checkout"),
        ("/preview/customer/orders/", "Customer Orders"),
        ("/preview/customer/order-detail/", "Customer Order Detail"),
        ("/preview/customer/order-confirmation/", "Customer Order Confirmation"),
        ("/preview/customer/credit/", "Customer Credit"),
        ("/preview/customer/activity/", "Customer Activity"),
        ("/preview/customer/requests/", "Customer Requests"),
        ("/preview/customer/request-detail/", "Customer Request Detail"),
        ("/preview/customer/profile/", "Customer Profile"),
        ("/preview/customer/settings/", "Customer Settings"),
    ]
    return render(request, "preview/index.html", {"preview_routes": preview_routes})


def existing_template_view(template_name):
    def view(request):
        return render(request, template_name)

    return view
