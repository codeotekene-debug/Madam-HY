from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_dashboard, name='report_dashboard'),
    path('', views.reports_dashboard, name='reports_dashboard'),
    path('dashboard/', views.reports_dashboard, name='dashboard'),
    path('sales/', views.sales_report_view, name='sales_report'),
    path('expenses/', views.expense_report_view, name='expense_report'),
    path('expense/', views.expense_report_view, name='expense_report_alias'),
    path('profit/', views.profit_report_view, name='profit_report'),
    path('growth/', views.growth_report_view, name='growth_report'),
]