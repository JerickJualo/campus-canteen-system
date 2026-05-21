
from django.urls import path
from .views import (
    add_inventory_item,
    delete_inventory_item,
    edit_inventory_item,
    inventory_dashboard,
    inventory_history,
    inventory_list,
    inventory_print_checklist,
    inventory_search,
    multi_item_restock,
    restock_inventory_item,
)

urlpatterns = [
    path('', inventory_dashboard, name='inventory_dashboard'),
    path('list/', inventory_list, name='inventory_list'),
    path('list/print-checklist/', inventory_print_checklist, name='inventory_print_checklist'),
    path('history/', inventory_history, name='inventory_history'),
    path('add/', add_inventory_item, name='add_inventory_item'),
    path('edit/<int:pk>/', edit_inventory_item, name='edit_inventory_item'),
    path('delete/<int:pk>/', delete_inventory_item, name='delete_inventory_item'),
    path('restock/<int:pk>/', restock_inventory_item, name='restock_inventory_item'),
    path('multi-restock/', multi_item_restock, name='multi_item_restock'),
    path('inventory-search/', inventory_search, name='inventory_search'),
]
