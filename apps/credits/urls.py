from django.urls import path

from . import views

app_name = 'credits'

urlpatterns = [
    path('', views.credit_account_list, name='credit_account_list'),
    path('list/', views.credit_account_list, name='credit_list'),
    path('accounts/', views.credit_account_list, name='accounts_list'),
    path('accounts/', views.credit_account_list, name='CREDIT_ACCOUNT_LIST'),
    path('customers/add-credit/', views.add_customer_credit_view, name='add_customer_credit'),
    path('add-credit/', views.add_customer_credit_view, name='add_credit'),
    path('add/', views.add_customer_credit_view, name='add_credit_shorthand'),
    path('transactions/', views.credit_transactions_view, name='credit_transactions'),
    path('payment/', views.credit_payment_page, name='credit_payment'),
    path('payment-page/', views.credit_payment_page, name='credit_payment_page'),
    path('reports/', views.credit_report_view, name='credit_report'),
    path('aging/', views.credit_report_view, name='credit_aging'),
    path('accounts/<uuid:account_id>/repay/', views.credit_repay, name='credit_repay_uuid'),
    path('accounts/<str:account_id>/repay/', views.credit_repay, name='credit_repay'),
    path('accounts/<uuid:account_id>/', views.credit_account_detail, name='credit_account_detail_uuid'),
    path('accounts/<str:account_id>/', views.credit_account_detail, name='credit_account_detail'),
    path('accounts/<uuid:account_id>/detail/', views.credit_account_detail, name='customer_credit_detail_uuid'),
    path('accounts/<str:account_id>/detail/', views.credit_account_detail, name='customer_credit_detail'),
    path('<uuid:account_id>/repay/', views.credit_repay, name='repay_shorthand_uuid'),
    path('<str:account_id>/repay/', views.credit_repay, name='repay_shorthand'),
    path('<uuid:account_id>/', views.credit_account_detail, name='detail_shorthand_uuid'),
    path('<str:account_id>/', views.credit_account_detail, name='detail_shorthand'),
]