from django.urls import path

from . import views

app_name = 'customer_orders'

urlpatterns = [
    path('', views.customer_dashboard_view, name='dashboard'),
    path('dashboard/', views.customer_dashboard_view, name='dashboard_alt'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/success/', views.customer_order_success_view, name='order_success'),
    path('orders/success/', views.customer_order_success_view, name='order_success_ref'),
    path('order-success/<int:order_id>/', views.customer_order_success_view, name='order_success_alt'),

    # Product catalog browsing and detail
    path('products/', views.customer_product_list, name='products'),
    path('products/', views.customer_product_list, name='customer_products'),
    path('products/<uuid:id>/', views.customer_product_detail, name='product_detail_uuid'),
    path('products/<int:id>/', views.customer_product_detail, name='product_detail_int'),
    path('products/<str:id>/', views.customer_product_detail, name='product_detail'),

    # Shopping cart management
    path('cart/', views.customer_cart_view, name='cart'),
    path('cart/items/', views.customer_cart_items_view, name='cart_items'),
    path('cart/items/<int:product_id>/', views.customer_cart_item_detail_view, name='cart_item_detail'),

    # Checkout & order placement
    path('checkout/', views.customer_checkout_view, name='checkout'),

    # Credit & activity
    path('credit/', views.customer_credit_view, name='credit'),
    path('activity/', views.customer_activity_view, name='activity'),
]

