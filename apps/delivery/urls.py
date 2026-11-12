from django.urls import path
from apps.delivery import views

app_name = 'delivery'

urlpatterns = [
    # Rider Portal
    path('rider/', views.rider_dashboard_view, name='rider_dashboard'),
    path('rider/assignments/', views.rider_assignments_view, name='rider_assignments'),
    path('rider/deliveries/', views.rider_deliveries_view, name='rider_deliveries'),
    path('rider/deliveries/<int:delivery_id>/', views.rider_delivery_detail_view, name='rider_delivery_detail'),
    path('rider/active/', views.rider_active_delivery_view, name='rider_active_delivery'),
    path('rider/history/', views.rider_history_view, name='rider_history'),
    path('rider/profile/', views.rider_profile_view, name='rider_profile'),
    path('rider/notifications/', views.rider_notifications_view, name='rider_notifications'),

    # Rider APIs
    path('rider/api/toggle-availability/', views.rider_toggle_availability_api, name='rider_toggle_availability'),
    path('rider/api/deliveries/<int:delivery_id>/accept/', views.rider_accept_delivery_api, name='rider_accept_delivery'),
    path('rider/api/deliveries/<int:delivery_id>/reject/', views.rider_reject_delivery_api, name='rider_reject_delivery'),
    path('rider/api/deliveries/<int:delivery_id>/pickup/', views.rider_confirm_pickup_api, name='rider_confirm_pickup'),
    path('rider/api/deliveries/<int:delivery_id>/verify-otp/', views.rider_verify_otp_api, name='rider_verify_otp'),
    path('rider/api/deliveries/<int:delivery_id>/report-failure/', views.rider_report_failure_api, name='rider_report_failure'),

    # Management Portal
    path('deliveries/', views.management_delivery_dashboard_view, name='management_dashboard'),
    path('deliveries/all/', views.management_all_deliveries_view, name='management_all'),
    path('deliveries/unassigned/', views.management_unassigned_deliveries_view, name='management_unassigned'),
    path('deliveries/active/', views.management_active_deliveries_view, name='management_active'),
    path('deliveries/completed/', views.management_completed_deliveries_view, name='management_completed'),
    path('deliveries/failed/', views.management_failed_deliveries_view, name='management_failed'),
    path('deliveries/<int:delivery_id>/', views.management_delivery_detail_view, name='management_detail'),
    path('deliveries/riders/', views.management_riders_view, name='management_riders'),
    path('deliveries/riders/create/', views.management_create_rider_api, name='management_create_rider'),
    path('deliveries/riders/<int:rider_id>/', views.management_rider_detail_view, name='management_rider_detail'),
    path('deliveries/riders/<int:rider_id>/toggle-status/', views.management_toggle_rider_status_api, name='management_toggle_rider_status'),
    path('deliveries/zones/', views.management_zones_view, name='management_zones'),
    path('deliveries/zones/<int:zone_id>/toggle/', views.management_zone_toggle_api, name='management_zone_toggle'),
    path('deliveries/settings/', views.management_settings_view, name='management_settings'),
    path('deliveries/reports/', views.management_reports_view, name='management_reports'),

    # Management APIs
    path('deliveries/api/<int:delivery_id>/assign/', views.management_assign_rider_api, name='management_assign_rider'),
    path('deliveries/api/<int:delivery_id>/override-pod/', views.management_pod_override_api, name='management_pod_override'),
    path('deliveries/api/<int:delivery_id>/reschedule/', views.management_reschedule_api, name='management_reschedule'),
    path('deliveries/api/<int:delivery_id>/return/', views.management_return_api, name='management_return'),
    path('deliveries/api/<int:delivery_id>/cancel/', views.management_cancel_api, name='management_cancel'),

    # Public & Customer APIs
    path('api/delivery/zones/', views.public_delivery_zones_api, name='public_zones'),
    path('api/delivery/track/<str:order_ref>/', views.customer_delivery_tracking_api, name='customer_track'),
]
