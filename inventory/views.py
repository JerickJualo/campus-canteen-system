
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.db import models, transaction
from django.db.models import Q
from django import forms

from .models import CATEGORY_CHOICES, InventoryItem, RestockHistory


def get_restock_user(request):
    if request.user.is_authenticated:
        return request.user
    return None


def record_restock(item, quantity_added, previous_quantity, request, note=''):
    return RestockHistory.objects.create(
        inventory_item=item,
        quantity_added=quantity_added,
        previous_quantity=previous_quantity,
        new_quantity=item.quantity_in_stock,
        restocked_by=get_restock_user(request),
        note=note,
    )

# --- Inventory Dashboard View ---
def inventory_dashboard(request):
    items = InventoryItem.objects.all()
    total_items = items.count()
    low_stock_items = items.filter(
        quantity_in_stock__lte=models.F('minimum_stock_level'),
        quantity_in_stock__gt=0,
    ).order_by('quantity_in_stock', 'item_name')
    out_of_stock_items = items.filter(quantity_in_stock=0).order_by('item_name')
    recent_restocks = RestockHistory.objects.select_related(
        'inventory_item',
        'restocked_by',
    )[:5]
    context = {
        'total_items': total_items,
        'total_low_stock': low_stock_items.count(),
        'total_out_of_stock': out_of_stock_items.count(),
        'low_stock_items': low_stock_items[:5],
        'out_of_stock_items': out_of_stock_items[:5],
        'recent_restocks': recent_restocks,
    }
    return render(request, 'inventory/inventory_dashboard.html', context)

# --- Multi-item Restock View and AJAX Search ---
def multi_item_restock(request):
    items = InventoryItem.objects.all().order_by('item_name')
    if request.method == 'POST':
        restock_data = request.POST
        updated = []
        for key in restock_data:
            if key.startswith('restock_'):
                pk = key.split('_')[1]
                try:
                    add_qty = int(restock_data[key])
                    if add_qty > 0:
                        with transaction.atomic():
                            item = InventoryItem.objects.select_for_update().get(pk=pk)
                            previous_quantity = item.quantity_in_stock
                            item.quantity_in_stock += add_qty
                            item.save()
                            record_restock(
                                item=item,
                                quantity_added=add_qty,
                                previous_quantity=previous_quantity,
                                request=request,
                                note='Multi-item restock',
                            )
                        updated.append(item.item_name)
                except (InventoryItem.DoesNotExist, ValueError):
                    continue
        return render(request, 'inventory/multi_item_restock.html', {
            'items': items,
            'success': True,
            'updated': updated,
        })
    return render(request, 'inventory/multi_item_restock.html', {'items': items})

def inventory_search(request):
    q = request.GET.get('q', '').strip()
    items = InventoryItem.objects.all().order_by('item_name')
    if q:
        items = items.filter(Q(item_name__icontains=q) | Q(category__icontains=q))
    results = [
        {
            'id': item.pk,
            'item_name': item.item_name,
            'category': item.category,
            'quantity_in_stock': item.quantity_in_stock,
            'minimum_stock_level': item.minimum_stock_level,
        }
        for item in items[:10]
    ]
    return JsonResponse({'results': results})


def inventory_history(request):
    history = RestockHistory.objects.select_related('inventory_item', 'restocked_by')
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search_query:
        history = history.filter(inventory_item__item_name__icontains=search_query)

    if category_filter:
        history = history.filter(inventory_item__category=category_filter)

    if date_from:
        history = history.filter(created_at__date__gte=date_from)

    if date_to:
        history = history.filter(created_at__date__lte=date_to)

    return render(request, 'inventory/inventory_history.html', {
        'history': history,
        'categories': [category for category, label in CATEGORY_CHOICES],
    })

def inventory_list(request):
    items = InventoryItem.objects.all()
    search_query = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '').strip()
    stock_filter = request.GET.get('stock_status', '').strip()
    sort_by = request.GET.get('sort', 'item_name')

    if search_query:
        items = items.filter(item_name__icontains=search_query)

    if category_filter:
        items = items.filter(category=category_filter)

    if stock_filter == 'low_stock':
        items = items.filter(quantity_in_stock__lte=models.F('minimum_stock_level'), quantity_in_stock__gt=0)
    elif stock_filter == 'out_of_stock':
        items = items.filter(quantity_in_stock=0)
    elif stock_filter == 'available':
        items = items.filter(quantity_in_stock__gt=models.F('minimum_stock_level'))

    if sort_by in ['item_name', 'category', 'quantity_in_stock', 'unit_price']:
        items = items.order_by(sort_by)
    else:
        items = items.order_by('item_name')

    categories = [category for category, label in CATEGORY_CHOICES]
    total_items = InventoryItem.objects.count()
    low_stock_count = InventoryItem.objects.filter(
        quantity_in_stock__lte=models.F('minimum_stock_level'),
        quantity_in_stock__gt=0,
    ).count()
    out_of_stock_count = InventoryItem.objects.filter(quantity_in_stock=0).count()

    return render(request, 'inventory/inventory_list.html', {
        'items': items,
        'categories': categories,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
    })


# Restock Inventory Item Form
class RestockItemForm(forms.Form):
    quantity_to_add = forms.IntegerField(
        min_value=1,
        label='Quantity to add',
        widget=forms.NumberInput(attrs={
            'placeholder': 'Enter restock amount',
            'class': 'restock-input',
        }),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'placeholder': 'Optional note',
            'class': 'restock-input',
        }),
    )

# Restock Inventory Item View
def restock_inventory_item(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        form = RestockItemForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item = InventoryItem.objects.select_for_update().get(pk=pk)
                quantity_to_add = form.cleaned_data['quantity_to_add']
                previous_quantity = item.quantity_in_stock
                item.quantity_in_stock += quantity_to_add
                item.save()
                record_restock(
                    item=item,
                    quantity_added=quantity_to_add,
                    previous_quantity=previous_quantity,
                    request=request,
                    note=form.cleaned_data['note'],
                )
            return redirect('inventory_list')
    else:
        form = RestockItemForm()
    return render(request, 'inventory/restock_inventory_item.html', {'form': form, 'item': item})

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
    item = get_object_or_404(InventoryItem, pk=pk)
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
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        item.delete()
        return redirect('inventory_list')
    return render(request, 'inventory/delete_inventory_item.html', {'item': item})
