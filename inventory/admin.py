from django.contrib import admin
from .models import InventoryItem

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
	list_display = ("item_name", "category", "unit_price", "quantity_in_stock", "minimum_stock_level", "status")
	list_filter = ("category", "status")
	search_fields = ("item_name",)
