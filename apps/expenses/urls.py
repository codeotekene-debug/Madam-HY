from django.urls import path

from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_list, name='expense_list'),
    path('list/', views.expense_list, name='list'),
    path('add/', views.expense_create, name='expense_create'),
    path('create/', views.expense_create, name='create'),
    path('categories/', views.expense_categories_view, name='category_list'),
    path('summary/', views.expense_summary_view, name='expense_summary'),
    path('<uuid:id>/approve/', views.expense_approve, name='expense_approve_uuid'),
    path('<str:id>/approve/', views.expense_approve, name='expense_approve'),
    path('<uuid:id>/reject/', views.expense_reject, name='expense_reject_uuid'),
    path('<str:id>/reject/', views.expense_reject, name='expense_reject'),
    path('<uuid:id>/', views.expense_detail, name='expense_detail_uuid'),
    path('<str:id>/', views.expense_detail, name='expense_detail'),
]