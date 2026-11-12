"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.views import customer_preferences_api, customer_settings_view
from apps.products.views import customer_product_list
from apps.sales.views import management_dashboard_view
from config.views import root_entry_view

 
urlpatterns = [
    path('', root_entry_view, name='root_index'),
    path('admin/', admin.site.urls),

    path("dashboard/", management_dashboard_view, name="management_dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    path("portal/login/", RedirectView.as_view(url="/accounts/portal/login/", permanent=False)),
    path("customer/settings/", customer_settings_view, name="customer_settings"),
    path("api/customer/preferences/", customer_preferences_api, name="api_customer_preferences"),
    path("customer/", include("apps.orders.customer_urls")),

    path("products/",include("apps.products.urls")),

    path("inventory/",include("apps.inventory.urls")),

    path("sales/",include("apps.sales.urls")),

    path("orders/",include("apps.orders.urls")),

    path("payments/",include("apps.payments.urls")),

    path("credits/",include("apps.credits.urls")),

    path("expenses/",include("apps.expenses.urls")),

    path("reports/",include("apps.reports.urls")),

    path("requests/",include("apps.requests.urls")),
    path("customer/requests/", include("apps.requests.customer_urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("activity-logs/", include("apps.activity_logs.urls")),
    path("logs/", RedirectView.as_view(url="/activity-logs/", permanent=False)),
    path("", include("apps.delivery.urls")),
    path("preview/", include("apps.preview.urls")),
]

from django.views.static import serve
from django.urls import re_path

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
else:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]

handler403 = 'config.views.custom_403_view'
handler404 = 'config.views.custom_404_view'
handler500 = 'config.views.custom_500_view'
