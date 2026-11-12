from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'products'

urlpatterns = [
    # Catalog (read-only)
    path('', views.products_list, name='list'),
    path('customer-products/', RedirectView.as_view(url='/customer/products/', permanent=False), name='customer_products'),
    path('categories/', views.categories_list, name='categories'),
    path('price-history/', views.product_price_history_list, name='price_history'),
    path('<int:product_id>/', views.product_detail, name='detail'),

    # Product management
    path('create/', views.product_create, name='create'),
    path('add/', views.product_create, name='add'),
    path('<int:product_id>/edit/', views.product_edit_view, name='edit'),
    path('<int:product_id>/update/', views.product_update, name='update'),
    path('<int:product_id>/deactivate/', views.product_deactivate, name='deactivate'),
    path('<int:product_id>/change-price/', views.product_change_price, name='change_price'),

    # Product image management
    path('<int:product_id>/images/', views.product_image_upload, name='upload_image'),
    path('<int:product_id>/images/<int:image_id>/', views.product_image_detail, name='image_detail'),

    # Category management
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:category_id>/update/', views.category_update, name='category_update'),
    path('categories/<int:category_id>/deactivate/', views.category_deactivate, name='category_deactivate'),
]