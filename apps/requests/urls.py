from django.urls import path

from . import views

app_name = 'requests'

urlpatterns = [
    path('', views.request_list, name='request_list'),
    path('list/', views.request_list, name='list'),
    path('my/', views.customer_request_list, name='customer_request_list'),
    path('create/', views.request_create, name='request_create'),
    path('add/', views.request_create, name='request_add'),
    path('<uuid:id>/status/', views.request_status_update, name='request_status_update_uuid'),
    path('<str:id>/status/', views.request_status_update, name='request_status_update'),
    path('<uuid:id>/assign/', views.request_assign, name='request_assign_uuid'),
    path('<str:id>/assign/', views.request_assign, name='request_assign'),
    path('<uuid:id>/', views.request_detail, name='request_detail_uuid'),
    path('<str:id>/', views.request_detail, name='request_detail'),
]