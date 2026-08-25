from django.urls import path

from . import views

urlpatterns = [
	path('', views.sale_create, name='create'),
	path('<int:sale_id>/complete/', views.sale_complete, name='complete'),
]