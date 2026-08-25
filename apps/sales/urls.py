from django.urls import path

from . import views

urlpatterns = [
	path('', views.sale_create, name='create'),
	path('reports/summary/', views.sale_report_summary, name='reports_summary'),
	path('<int:sale_id>/complete/', views.sale_complete, name='complete'),
	path('<int:sale_id>/', views.sale_detail, name='detail'),
]