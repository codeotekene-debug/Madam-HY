from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_user, name='login'),
    path('portal/login/', views.staff_login_view, name='staff_login'),
    path('logout/', views.logout_user, name='logout'),
    path('register/', views.register_user, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('settings/', views.customer_settings_view, name='settings'),
    path('settings/notifications/', views.customer_preferences_api, name='settings_notifications'),
    path('preferences/', views.customer_preferences_api, name='preferences'),
]