from django.urls import path
from . import views

urlpatterns = [
    path('', views.customer_request_list, name='customer_requests_list'),
    path('create/', views.request_create, name='customer_request_create'),
    path('<uuid:id>/', views.request_detail, name='customer_request_detail_uuid'),
    path('<str:id>/', views.request_detail, name='customer_request_detail'),
]
