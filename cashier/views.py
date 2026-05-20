from collections import _OrderedDictItemsView, OrderedDict
from datetime import timedelta, datetime, date
import os

from config import settings
from .models import Order   
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from cashier.models import Sale, SaleItem, Receipt
from inventory.models import InventoryItem
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Sum, F
from django import forms
import django.db.models as models
from django.http import JsonResponse

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


def cashier_search(request):
    query = request.GET.get('q', '').strip()

    items = InventoryItem.objects.filter(
        quantity_in_stock__gt=0,
        item_name__icontains=query
    )[:8]

    results = []

    for item in items:
        results.append({
            'id': item.id,
            'item_name': item.item_name,
            'category': item.category,
            'price': str(item.unit_price),
            'stock': item.quantity_in_stock,
        })

    return JsonResponse({'results': results})


def add_to_cart(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    qty = int(request.GET.get('qty', 1))

    if item_id in cart:
        new_qty = cart[item_id]['quantity'] + qty

        if new_qty <= item.quantity_in_stock:
            cart[item_id]['quantity'] = new_qty
        else:
            cart[item_id]['quantity'] = item.quantity_in_stock
        
    else:
        cart[item_id] = {
            'name': item.item_name,
            'price': float(item.unit_price),
            'quantity': qty
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

        # deduct stock and save the completed sale for reporting
        low_stock_alerts = []

        sale = Sale.objects.create(
            total_amount=total,
            created_at=timezone.now()
        )

        for item_id, item in cart.items():
            inventory_item = InventoryItem.objects.get(id=item_id)
            inventory_item.quantity_in_stock -= item['quantity']
            inventory_item.save()

            if inventory_item.quantity_in_stock <= inventory_item.minimum_stock_level:
                low_stock_alerts.append(
                    f"{inventory_item.item_name} is low on stock ({inventory_item.quantity_in_stock} left)"
                )

            SaleItem.objects.create(
                sale=sale,
                item_name=item['name'],
                quantity=item['quantity'],
                price=item['price']
            )

        # clear cart after successful transaction
        request.session['cart'] = {}

        # Create receipt for this transaction
        receipt = Receipt.objects.create(
            sale=sale,
            receipt_number=Receipt.generate_receipt_number(),
            cashier_name='Cashier',
            payment_method='Cash'
        )

        return render(request, 'cashier/cashier_home.html', {
            'success': 'Transaction completed successfully.',
            'change': change,
            'cash': cash,
            'total': 0,
            'items': InventoryItem.objects.filter(quantity_in_stock__gt=0),
            'cart': {},
            'low_stock_alerts': low_stock_alerts,
            'receipt_id': receipt.id,
            'receipt_number': receipt.receipt_number,
        })

    return redirect('cashier')

def complete_transaction(request):
    if request.method == "POST":
        cart = request.session.get('cart', [])
        
        total = sum(item['price'] * item['qty'] for item in cart)

        sale = Sale.objects.create(
            total_amount=total,
            created_at=timezone.now()
        )

        # SAVE ITEMS
        for item in cart:
            SaleItem.objects.create(
                sale=sale,
                item_name=item['name'],
                quantity=item['qty'],
                price=item['price']
            )

        # CLEAR CART
        request.session['cart'] = []

        return redirect('cashier')
    


def daily_report(request, year=None, month=None, day=None):
    from django.db.models import Q, F
    from collections import defaultdict

    if year and month and day:
        report_date = date(year, month, day)
    else:
        report_date = now().date()

    sales = Sale.objects.filter(
        created_at__date=report_date
    ).order_by('-created_at')

    total = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get all sale items for the report date
    sale_items = SaleItem.objects.filter(
        sale__created_at__date=report_date
    )
    
    # Total items sold (sum of quantities)
    total_items_sold = sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Best-selling items for the day
    from django.db.models import Sum as DjangoSum
    best_sellers = sale_items.values('item_name').annotate(
        total_qty=DjangoSum('quantity'),
        total_revenue=DjangoSum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-total_qty')[:5]
    
    # All items sold today with quantities
    items_sold = sale_items.values('item_name').annotate(
        total_qty=DjangoSum('quantity'),
        unit_price=F('price'),
        total_revenue=DjangoSum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-total_qty')
    
    # Low-stock items
    low_stock_items = InventoryItem.objects.filter(
        quantity_in_stock__lte=F('minimum_stock_level')
    ).values('item_name', 'quantity_in_stock', 'minimum_stock_level')
    
    # Fast-moving items (items sold today with current stock)
    sold_item_names = set(sale_items.values_list('item_name', flat=True))
    fast_moving_items = InventoryItem.objects.filter(
        item_name__in=sold_item_names
    ).values('item_name', 'quantity_in_stock', 'unit_price').order_by('-quantity_in_stock')

    return render(request, 'report/daily.html', {
        'sales': sales,
        'total': total,
        'report_date': report_date,
        'transaction_count': sales.count(),
        'total_items_sold': total_items_sold,
        'best_sellers': best_sellers,
        'items_sold': items_sold,
        'low_stock_items': low_stock_items,
        'fast_moving_items': fast_moving_items,
    })
    
def monthly_report(request, year=None, month=None):
    from django.db.models import Sum as DjangoSum, Count
    from collections import defaultdict

    if year and month:
        report_year = int(year)
        report_month = int(month)
    else:
        now_dt = now()
        report_year = now_dt.year
        report_month = now_dt.month

    sales = Sale.objects.filter(
        created_at__year=report_year,
        created_at__month=report_month
    ).order_by('-created_at')

    total = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get all sale items for the month
    sale_items = SaleItem.objects.filter(
        sale__created_at__year=report_year,
        sale__created_at__month=report_month
    )
    
    # Total items sold for the month
    total_items_sold = sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Top-selling items of the month
    best_sellers = sale_items.values('item_name').annotate(
        total_qty=DjangoSum('quantity'),
        total_revenue=DjangoSum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-total_qty')[:5]
    
    # Lowest-selling items
    lowest_sellers = sale_items.values('item_name').annotate(
        total_qty=DjangoSum('quantity'),
        total_revenue=DjangoSum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('total_qty')[:5]
    
    # Daily sales summary
    from inventory.models import RestockHistory
    daily_sales = sale_items.values('sale__created_at__date').annotate(
        daily_qty=DjangoSum('quantity'),
        daily_revenue=DjangoSum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-sale__created_at__date')
    
    # Total restocks made during the month
    restocks = RestockHistory.objects.filter(
        created_at__year=report_year,
        created_at__month=report_month
    )
    total_restocks_count = restocks.count()
    total_quantity_restocked = restocks.aggregate(Sum('quantity_added'))['quantity_added__sum'] or 0
    
    # Items that frequently ran low or out of stock (from restock history)
    low_stock_items = restocks.values('inventory_item__item_name').annotate(
        restock_count=Count('id'),
        total_qty_added=DjangoSum('quantity_added')
    ).order_by('-restock_count')[:5]

    month_name = datetime(report_year, report_month, 1).strftime('%B')
    
    return render(request, 'report/monthly.html', {
        'sales': sales,
        'total': total,
        'month': report_month,
        'year': report_year,
        'month_name': month_name,
        'transaction_count': sales.count(),
        'total_items_sold': total_items_sold,
        'best_sellers': best_sellers,
        'lowest_sellers': lowest_sellers,
        'daily_sales': daily_sales,
        'low_stock_items': low_stock_items,
        'total_restocks_count': total_restocks_count,
        'total_quantity_restocked': total_quantity_restocked,
    })


def delete_daily_report(request):
    if request.method == 'POST':
        today = now().date()
        # Delete all sales for today
        sales_to_delete = Sale.objects.filter(created_at__date=today)
        count = sales_to_delete.count()
        sales_to_delete.delete()
        
        # Also delete related sale items (cascade should handle this, but let's be explicit)
        SaleItem.objects.filter(sale__created_at__date=today).delete()
        
        messages.success(request, f'Successfully deleted {count} sales records for today.')
        return redirect('daily_report')
    return redirect('daily_report')


def delete_monthly_report(request):
    if request.method == 'POST':
        today = now()
        current_month = today.month
        current_year = today.year
        
        # Delete all sales for the current month
        sales_to_delete = Sale.objects.filter(
            created_at__year=current_year,
            created_at__month=current_month
        )
        count = sales_to_delete.count()
        sales_to_delete.delete()
        
        # Also delete related sale items (cascade should handle this, but let's be explicit)
        SaleItem.objects.filter(
            sale__created_at__year=current_year,
            sale__created_at__month=current_month
        ).delete()
        
        messages.success(request, f'Successfully deleted {count} sales records for {today.strftime("%B %Y")}.')
        return redirect('monthly_report')
    return redirect('monthly_report')


def daily_report_history(request):
    from django.db.models.functions import TruncDate
    from django.db.models import Count

    daily_history_qs = Sale.objects.annotate(
        report_date=TruncDate('created_at')
    ).values('report_date').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_date')[:30]

    daily_history = list(daily_history_qs)

    return render(request, 'report/daily_report_history.html', {
        'daily_history': daily_history,
    })


def monthly_report_history(request):
    from django.db.models.functions import TruncMonth
    from django.db.models import Count

    monthly_history_qs = Sale.objects.annotate(
        report_month=TruncMonth('created_at')
    ).values('report_month').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_month')[:12]

    monthly_history = list(monthly_history_qs)

    return render(request, 'report/monthly_report_history.html', {
        'monthly_history': monthly_history,
    })


def report_history(request):
    from django.db.models.functions import TruncDate, TruncMonth
    from django.db.models import Count

    daily_history = Sale.objects.annotate(
        report_date=TruncDate('created_at')
    ).values('report_date').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_date')[:30]

    monthly_history = Sale.objects.annotate(
        report_month=TruncMonth('created_at')
    ).values('report_month').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_month')[:12]

    return render(request, 'report/report_history.html', {
        'daily_history': daily_history,
        'monthly_history': monthly_history,
    })


def generate_receipt(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    
    # Check if receipt already exists
    if hasattr(sale, 'receipt'):
        receipt = sale.receipt
    else:
        # Create new receipt
        receipt = Receipt.objects.create(
            sale=sale,
            receipt_number=Receipt.generate_receipt_number(),
            cashier_name='Cashier',
            payment_method='Cash'
        )
    
    # Get sale items with calculated subtotals
    sale_items = SaleItem.objects.filter(sale=sale)
    sale_items_with_subtotal = []
    for item in sale_items:
        item.subtotal = item.quantity * item.price
        sale_items_with_subtotal.append(item)
    
    context = {
        'receipt': receipt,
        'sale': sale,
        'sale_items': sale_items_with_subtotal,
        'total_items': sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0,
    }
    
    return render(request, 'cashier/receipt.html', context)