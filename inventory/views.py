from django.shortcuts import render, redirect
from .models import InventoryItem
from django import forms

# Inventory List View
def inventory_list(request):
    items = InventoryItem.objects.all().order_by('item_name')
    return render(request, 'inventory/inventory_list.html', {'items': items})

# Inventory Add Item Form
class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['item_name', 'category', 'unit_price', 'quantity_in_stock', 'minimum_stock_level']

# Add Inventory Item View
def add_inventory_item(request):
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inventory_list')
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/add_inventory_item.html', {'form': form})


# Edit Inventory Item View
def edit_inventory_item(request, pk):
    item = InventoryItem.objects.get(pk=pk)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            return redirect('inventory_list')
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/edit_inventory_item.html', {'form': form, 'item': item})


# Delete Inventory Item View
def delete_inventory_item(request, pk):
    item = InventoryItem.objects.get(pk=pk)
    if request.method == 'POST':
        item.delete()
        return redirect('inventory_list')
    return render(request, 'inventory/delete_inventory_item.html', {'item': item})