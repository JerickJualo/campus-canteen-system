from django.db import models
from django.conf import settings

# Inventory categories
CATEGORY_CHOICES = [
	("Drinks", "Drinks"),
	("Snacks", "Snacks"),
	("Noodles", "Noodles"),
	("Dish", "Dish"),
	("Others", "Others"),
]

# Status choices
STATUS_CHOICES = [
	("Available", "Available"),
	("Out of Stock", "Out of Stock"),
]

class InventoryItem(models.Model):
	item_name = models.CharField(max_length=100)
	category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
	unit_price = models.DecimalField(max_digits=8, decimal_places=2)
	quantity_in_stock = models.PositiveIntegerField()
	minimum_stock_level = models.PositiveIntegerField()

	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Available")

	def save(self, *args, **kwargs):
		# Automatically update status based on quantity_in_stock
		if self.quantity_in_stock == 0:
			self.status = "Out of Stock"
		else:
			self.status = "Available"
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.item_name} ({self.category})"


class RestockHistory(models.Model):
	inventory_item = models.ForeignKey(
		InventoryItem,
		on_delete=models.CASCADE,
		related_name="restock_history",
	)
	quantity_added = models.PositiveIntegerField()
	previous_quantity = models.PositiveIntegerField()
	new_quantity = models.PositiveIntegerField()
	restocked_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
	)
	note = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		verbose_name_plural = "Restock history"

	def __str__(self):
		return f"{self.inventory_item.item_name} +{self.quantity_added}"
