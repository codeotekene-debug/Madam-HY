from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='list'),
    path('reports/summary/', views.inventory_report_summary, name='reports_summary'),
    path('reports/movements/', views.inventory_report_movements, name='reports_movements'),
    path('reports/low-stock/', views.inventory_report_low_stock, name='reports_low_stock'),
    path('<int:inventory_id>/adjust/', views.inventory_adjust, name='adjust'),
    path('<int:inventory_id>/movements/', views.inventory_movements, name='movements'),
    path('<int:inventory_id>/', views.inventory_detail, name='detail'),
]
