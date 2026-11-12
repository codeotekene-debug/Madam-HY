from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
	path('', views.order_list, name='list'),
    path('reports/summary/', views.order_summary, name='summary'),
	path('<int:order_id>/status/', views.order_status_update, name='status_update'),
	path('<int:order_id>/convert-to-sale/', views.order_convert_to_sale, name='convert_to_sale'),
	path('<int:order_id>/', views.order_detail, name='detail'),
	path('customer/dashboard/', views.customer_dashboard_view, name='customer_dashboard'),
]