from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
	path('', views.sale_create, name='create'),
	path('pos/', views.pos_view, name='pos'),
	path('checkout/', views.sales_checkout_view, name='checkout'),
	path('receipt/', views.sales_receipt_view, name='receipt'),
	path('history/', views.sales_history_view, name='history'),
	path('customers/search/', views.customer_search_view, name='customer_search'),
	path('dashboard/', views.management_dashboard_view, name='dashboard'),
	path('summary/', views.sale_report_summary, name='summary'),
	path('reports/summary/', views.sale_report_summary, name='reports_summary'),
	path('<int:sale_id>/complete/', views.sale_complete, name='complete'),
	path('<int:sale_id>/', views.sale_detail, name='detail'),
]
