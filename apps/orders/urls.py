from django.urls import path

from . import views

urlpatterns = []

urlpatterns = [
	path('', views.order_list, name='list'),
	path('<int:order_id>/', views.order_detail, name='detail'),
]