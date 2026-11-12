from django.urls import path

from . import views

app_name = 'activity_logs'

urlpatterns = [
    path('', views.activity_log_list, name='list'),
    path('metrics/', views.activity_log_metrics, name='metrics'),
    path('<int:id>/', views.activity_log_detail, name='detail'),
]
