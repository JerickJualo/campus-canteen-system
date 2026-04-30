from django.contrib import admin
from .models import InventoryItem, RestockHistory

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
	list_display = ("item_name", "category", "unit_price", "quantity_in_stock", "minimum_stock_level", "status")
	list_filter = ("category", "status")
	search_fields = ("item_name",)


@admin.register(RestockHistory)
class RestockHistoryAdmin(admin.ModelAdmin):
	list_display = ("inventory_item", "quantity_added", "previous_quantity", "new_quantity", "restocked_by", "created_at")
	list_filter = ("created_at", "inventory_item__category")
	search_fields = ("inventory_item__item_name", "note")
	readonly_fields = ("inventory_item", "quantity_added", "previous_quantity", "new_quantity", "restocked_by", "note", "created_at")
