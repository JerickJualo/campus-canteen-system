
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.db import models, transaction
from django.db.models import Q
from django import forms
from django.utils import timezone

from .models import CATEGORY_CHOICES, Category, InventoryItem, RestockHistory
from accounts.decorators import admin_required
from core.models import log_activity


def get_request_role(request):
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        return request.user.profile.role
    return 'cashier'


def get_restock_user(request):
    if request.user.is_authenticated:
        return request.user
    return None


def record_restock(item, quantity_added, previous_quantity, request, note=''):
    record = RestockHistory.objects.create(
        inventory_item=item,
        quantity_added=quantity_added,
        previous_quantity=previous_quantity,
        new_quantity=item.quantity_in_stock,
        restocked_by=get_restock_user(request),
        note=note,
    )
    log_activity(
        get_restock_user(request),
        'restock',
        f'Restocked {item.item_name}: {previous_quantity} to {item.quantity_in_stock}',
        item.item_name,
    )
    return record


def get_category_names():
    ensure_default_categories()
    return list(Category.objects.values_list('name', flat=True))


def ensure_default_categories():
    existing_item_categories = InventoryItem.objects.exclude(category='').values_list('category', flat=True).distinct()
    category_names = [category for category, label in CATEGORY_CHOICES]
    category_names.extend(existing_item_categories)

    for category_name in category_names:
        clean_name = category_name.strip()
        if clean_name:
            Category.objects.get_or_create(name=clean_name)


# --- Inventory Dashboard View ---
@admin_required
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
@admin_required
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
        if updated:
            messages.success(request, f"Successfully restocked {len(updated)} item(s): {', '.join(updated)}.")
        else:
            messages.error(request, 'Please add at least one item with a restock amount greater than 0.')

        return render(request, 'inventory/multi_item_restock.html', {
            'items': items,
            'success': bool(updated),
            'updated': updated,
        })
    return render(request, 'inventory/multi_item_restock.html', {'items': items})

@admin_required
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


@admin_required
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
        'categories': get_category_names(),
        'is_monitor': get_request_role(request) == 'monitor',
    })

def get_filtered_inventory_items(request):
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

    return items, {
        'search_query': search_query,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'sort_by': sort_by,
    }


def get_inventory_summary():
    total_items = InventoryItem.objects.count()
    low_stock_count = InventoryItem.objects.filter(
        quantity_in_stock__lte=models.F('minimum_stock_level'),
        quantity_in_stock__gt=0,
    ).count()
    out_of_stock_count = InventoryItem.objects.filter(quantity_in_stock=0).count()

    return {
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
    }


@admin_required
def inventory_list(request):
    items, filter_context = get_filtered_inventory_items(request)
    categories = get_category_names()
    summary = get_inventory_summary()
    is_monitor = get_request_role(request) == 'monitor'

    return render(request, 'inventory/inventory_list.html', {
        'items': items,
        'categories': categories,
        'is_monitor': is_monitor,
        **summary,
        **filter_context,
    })


@admin_required
def inventory_print_checklist(request):
    items, filter_context = get_filtered_inventory_items(request)
    summary = get_inventory_summary()

    return render(request, 'inventory/inventory_print_checklist.html', {
        'items': items,
        'printed_at': timezone.localtime(),
        **summary,
        **filter_context,
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
@admin_required
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
            messages.success(
                request,
                f'{item.item_name} was restocked successfully. Added {quantity_to_add}; stock is now {item.quantity_in_stock}.',
            )
            return redirect('inventory_list')
        messages.error(request, 'Please enter a valid restock amount greater than 0.')
    else:
        form = RestockItemForm()
    return render(request, 'inventory/restock_inventory_item.html', {'form': form, 'item': item})

# Inventory Add Item Form
class InventoryItemForm(forms.ModelForm):
    new_category = forms.CharField(
        required=False,
        max_length=50,
        label='New category',
        help_text='Use this only if the category is not in the list.',
        widget=forms.TextInput(attrs={
            'placeholder': 'Example: Desserts',
        }),
    )

    class Meta:
        model = InventoryItem
        fields = ['item_name', 'category', 'unit_price', 'quantity_in_stock', 'minimum_stock_level']
        widgets = {
            'category': forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = get_category_names()
        self.fields['category'].choices = [('', 'Select category')] + [
            (category, category) for category in categories
        ]
        self.fields['category'].widget.choices = self.fields['category'].choices
        self.fields['category'].required = False

    def clean_item_name(self):
        item_name = self.cleaned_data['item_name'].strip()
        if not item_name:
            raise forms.ValidationError('Item name is required.')

        duplicate_items = InventoryItem.objects.filter(item_name__iexact=item_name)
        if self.instance.pk:
            duplicate_items = duplicate_items.exclude(pk=self.instance.pk)

        if duplicate_items.exists():
            raise forms.ValidationError('An inventory item with this name already exists.')

        return item_name

    def clean_new_category(self):
        new_category = (self.cleaned_data.get('new_category') or '').strip()
        if len(new_category) > 50:
            raise forms.ValidationError('Category name must be 50 characters or fewer.')
        return new_category

    def clean(self):
        cleaned_data = super().clean()
        category = (cleaned_data.get('category') or '').strip()
        new_category = (cleaned_data.get('new_category') or '').strip()

        if not category and not new_category:
            raise forms.ValidationError('Please choose an existing category or enter a new one.')

        if new_category:
            cleaned_data['category'] = new_category

        return cleaned_data

    def clean_unit_price(self):
        unit_price = self.cleaned_data['unit_price']
        if unit_price <= 0:
            raise forms.ValidationError('Unit price must be greater than 0.')
        return unit_price

    def clean_minimum_stock_level(self):
        minimum_stock_level = self.cleaned_data['minimum_stock_level']
        if minimum_stock_level < 1:
            raise forms.ValidationError('Minimum stock level must be at least 1.')
        return minimum_stock_level

    def clean_quantity_in_stock(self):
        quantity_in_stock = self.cleaned_data['quantity_in_stock']
        if quantity_in_stock < 0:
            raise forms.ValidationError('Quantity in stock cannot be negative.')
        return quantity_in_stock

    def save(self, commit=True):
        item = super().save(commit=False)
        category = self.cleaned_data['category'].strip()
        item.category = category
        Category.objects.get_or_create(name=category)

        if commit:
            item.save()

        return item

# Add Inventory Item View
@admin_required
def add_inventory_item(request):
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f'{item.item_name} was added successfully.')
            log_activity(request.user, 'inventory', f'Added inventory item {item.item_name}', item.item_name)
            return redirect('inventory_list')
        messages.error(request, 'Please correct the errors below before adding the item.')
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/add_inventory_item.html', {'form': form})


# Edit Inventory Item View
@admin_required
def edit_inventory_item(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            item = form.save()
            messages.success(request, f'{item.item_name} was updated successfully.')
            log_activity(request.user, 'inventory', f'Updated inventory item {item.item_name}', item.item_name)
            return redirect('inventory_list')
        messages.error(request, 'Please correct the errors below before saving changes.')
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/edit_inventory_item.html', {'form': form, 'item': item})


# Delete Inventory Item View
@admin_required
def delete_inventory_item(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        if item.sale_items.exists() or item.restock_history.exists():
            messages.error(
                request,
                f'{item.item_name} cannot be deleted because it has sales or restock history. Set its stock to 0 instead.'
            )
            return redirect('inventory_list')

        item_name = item.item_name
        item.delete()
        messages.success(request, f'{item_name} was deleted successfully.')
        log_activity(request.user, 'inventory', f'Deleted inventory item {item_name}', item_name)
        return redirect('inventory_list')
    return render(request, 'inventory/delete_inventory_item.html', {'item': item})
