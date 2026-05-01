from django.urls import path
from .views import (
    cashier_home, 
    add_to_cart, 
    remove_from_cart,
    increase_quantity,
    decrease_quantity,
    checkout
)

urlpatterns = [
    path('', cashier_home, name='cashier'),
    path('add/<int:item_id>/', add_to_cart, name='add_to_cart'),
    path('remove/<int:item_id>/', remove_from_cart, name='remove_from_cart'),
    path('increase/<int:item_id>/', increase_quantity, name='increase_quantity'),
    path('decrease/<int:item_id>/', decrease_quantity, name='decrease_quantity'),
    path('checkout/', checkout, name='checkout'),
]