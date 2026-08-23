from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='list'),
    path('<int:inventory_id>/movements/', views.inventory_movements, name='movements'),
    path('<int:inventory_id>/', views.inventory_detail, name='detail'),
]
