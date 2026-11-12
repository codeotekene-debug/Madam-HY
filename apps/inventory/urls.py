from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='list'),
    path('low-stock/', views.inventory_low_stock_view, name='low_stock'),
    path('history/', views.inventory_history_view, name='history'),
    path('adjust/', views.inventory_add_stock_view, name='add_stock'),
    path('valuation/', views.inventory_valuation_view, name='valuation'),
    path('reports/summary/', views.inventory_report_summary, name='reports_summary'),
    path('reports/movements/', views.inventory_report_movements, name='reports_movements'),
    path('reports/low-stock/', views.inventory_report_low_stock, name='reports_low_stock'),
    path('<int:inventory_id>/adjust/', views.inventory_adjust, name='adjust'),
    path('<int:inventory_id>/movements/', views.inventory_movements, name='movements'),
    path('<int:inventory_id>/', views.inventory_detail, name='detail'),
]
