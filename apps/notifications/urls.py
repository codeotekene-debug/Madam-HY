from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_inbox, name='inbox'),
    path('list/', views.notification_inbox, name='list'),
    path('unread-count/', views.unread_count_api, name='unread_count'),
    path('read-all/', views.mark_all_read, name='mark_all_read'),
    path('<int:id>/read/', views.mark_notification_read, name='mark_read'),
    path('<str:id>/read/', views.mark_notification_read, name='mark_read_str'),
    path('<int:id>/unread/', views.mark_notification_unread, name='mark_unread'),
    path('<str:id>/unread/', views.mark_notification_unread, name='mark_unread_str'),
]
