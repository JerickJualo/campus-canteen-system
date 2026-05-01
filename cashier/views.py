from django.shortcuts import render, redirect, get_object_or_404
from inventory.models import InventoryItem

def cashier_home(request):
    search_query = request.GET.get('search', '').strip()
    items = InventoryItem.objects.filter(quantity_in_stock__gt=0)

    if search_query:
        items = items.filter(item_name__icontains=search_query)

    cart = request.session.get('cart', {})

    total = sum(
        item['price'] * item['quantity']
        for item in cart.values()
    )

    return render(request, 'cashier/cashier_home.html', {
        'items': items,
        'cart': cart,
        'total': total,
    })


def add_to_cart(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)

    cart = request.session.get('cart', {})

    item_id = str(item_id)

    if item_id in cart:
        if cart[item_id]['quantity'] < item.quantity_in_stock:
            cart[item_id]['quantity'] += 1
    else:
        cart[item_id] = {
            'name': item.item_name,
            'price': float(item.unit_price),
            'quantity': 1
        }

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


def remove_from_cart(request, item_id):
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    if item_id in cart:
        del cart[item_id]

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


def increase_quantity(request, item_id):
    cart = request.session.get('cart', {})
    item = get_object_or_404(InventoryItem, id=item_id)
    item_id = str(item_id)

    if item_id in cart:
        if cart[item_id]['quantity'] < item.quantity_in_stock:
            cart[item_id]['quantity'] += 1

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


def decrease_quantity(request, item_id):
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    if item_id in cart:
        cart[item_id]['quantity'] -= 1

        if cart[item_id]['quantity'] <= 0:
            del cart[item_id]

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


def checkout(request):
    cart = request.session.get('cart', {})

    if not cart:
        return redirect('cashier')

    total = 0

    for item_id, item in cart.items():
        total += item['price'] * item['quantity']

    if request.method == 'POST':
        cash = float(request.POST.get('cash'))

        if cash < total:
            return render(request, 'cashier/cashier_home.html', {
                'error': 'Insufficient payment.',
                'cash': cash,
                'total': total,
                'change': 0,
                'items': InventoryItem.objects.all(),
                'cart': cart
            })

        change = cash - total

        for item_id, item in cart.items():
            inventory_item = InventoryItem.objects.get(id=item_id)

            if item['quantity'] > inventory_item.quantity_in_stock:
                return render(request, 'cashier/cashier_home.html', {
                    'error': f'Not enough stock for {inventory_item.item_name}.',
                    'items': InventoryItem.objects.filter(quantity_in_stock__gt=0),
                    'cart': cart,
                    'total': total
                })

        # deduct stock
        low_stock_alerts = []

        for item_id, item in cart.items():
            inventory_item = InventoryItem.objects.get(id=item_id)
            inventory_item.quantity_in_stock -= item['quantity']
            inventory_item.save()

            if inventory_item.quantity_in_stock <= inventory_item.minimum_stock_level:
                low_stock_alerts.append(
                    f"{inventory_item.item_name} is low on stock ({inventory_item.quantity_in_stock} left)"
                )

        # clear cart after successful transaction
        request.session['cart'] = {}

        return render(request, 'cashier/cashier_home.html', {
            'success': 'Transaction completed successfully.',
            'change': change,
            'cash': cash,
            'total': total,
            'items': InventoryItem.objects.filter(quantity_in_stock__gt=0),
            'cart': {},
            'low_stock_alerts': low_stock_alerts,
        })

    return redirect('cashier')