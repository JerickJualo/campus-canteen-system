from django.urls import path
from .views import cashier_home

urlpatterns = [
    path('', cashier_home, name='cashier'),
]