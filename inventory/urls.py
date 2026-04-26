from django.urls import path
from .views import inventory_home

urlpatterns = [
    path('', inventory_home, name='inventory'),
]