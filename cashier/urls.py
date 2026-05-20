from django.http import HttpResponse
from django.urls import path
from . import views

from .views import (
    cashier_home,
    cashier_search, 
    add_to_cart, 
    remove_from_cart,
    increase_quantity,
    decrease_quantity,
    checkout,
    generate_receipt
)

urlpatterns = [
    path('', cashier_home, name='cashier'),
    path('search/', cashier_search, name='cashier_search'),
    path('add/<int:item_id>/', add_to_cart, name='add_to_cart'),
    path('remove/<int:item_id>/', remove_from_cart, name='remove_from_cart'),
    path('increase/<int:item_id>/', increase_quantity, name='increase_quantity'),
    path('decrease/<int:item_id>/', decrease_quantity, name='decrease_quantity'),
    path('checkout/', checkout, name='checkout'),
    path('receipt/<int:sale_id>/', generate_receipt, name='generate_receipt'),
    path('reports/daily/', views.daily_report, name='daily_report'),
    path('reports/daily/<int:year>/<int:month>/<int:day>/', views.daily_report, name='daily_report_by_date'),
    path('reports/monthly/', views.monthly_report, name='monthly_report'),
    path('reports/monthly/<int:year>/<int:month>/', views.monthly_report, name='monthly_report_by_month'),
    path('reports/daily/delete/', views.delete_daily_report, name='delete_daily_report'),
    path('reports/monthly/delete/', views.delete_monthly_report, name='delete_monthly_report'),
    path('reports/history/', views.report_history, name='report_history'),
    path('reports/history/daily/', views.daily_report_history, name='daily_report_history'),
    path('reports/history/monthly/', views.monthly_report_history, name='monthly_report_history'),
   path('daily/cashier/', views.daily_report, name='cashier_home'),
    path('receipt/<int:receipt_id>/delete/', views.delete_receipt, name='delete_receipt'),
]
