
from django.urls import path
from .views import inventory_list, add_inventory_item, edit_inventory_item, delete_inventory_item, restock_inventory_item

urlpatterns = [
    path('', inventory_list, name='inventory_list'),
    path('add/', add_inventory_item, name='add_inventory_item'),
    path('edit/<int:pk>/', edit_inventory_item, name='edit_inventory_item'),
    path('delete/<int:pk>/', delete_inventory_item, name='delete_inventory_item'),
    path('restock/<int:pk>/', restock_inventory_item, name='restock_inventory_item'),
]