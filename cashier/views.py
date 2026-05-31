from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import os

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.utils.timezone import now
from django.db import transaction
from django.db.models import Q, Sum, F
import django.db.models as models
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required

from accounts.decorators import admin_required, cashier_required
from cashier.models import Sale, SaleItem, Receipt
from inventory.models import InventoryItem


def get_request_role(request):
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        return request.user.profile.role
    return 'cashier'


@cashier_required
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

    # Fetch recent receipts for the receipt history section
    recent_receipts = Receipt.objects.select_related('sale').order_by('-created_at')[:20]

    return render(request, 'cashier/cashier_home.html', {
        'items': items,
        'cart': cart,
        'total': total,
        'recent_receipts': recent_receipts,
    })


@cashier_required
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


@cashier_required
def add_to_cart(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    try:
        qty = int(request.GET.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1

    if qty < 1:
        qty = 1

    # Check if we should set the exact amount or add to it
    if request.GET.get('set_exact') == '1':
        new_qty = qty
    else:
        if item_id in cart:
            new_qty = cart[item_id]['quantity'] + qty
        else:
            new_qty = qty

    if new_qty <= item.quantity_in_stock:
        cart[item_id] = {
            'name': item.item_name,
            'price': float(item.unit_price),
            'quantity': new_qty
        }
    else:
        cart[item_id] = {
            'name': item.item_name,
            'price': float(item.unit_price),
            'quantity': item.quantity_in_stock
        }

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


@cashier_required
def remove_from_cart(request, item_id):
    cart = request.session.get('cart', {})
    item_id = str(item_id)

    if item_id in cart:
        del cart[item_id]

    request.session['cart'] = cart
    search_query = request.GET.get('search', '')
    return redirect(f'/cashier/?search={search_query}')


@cashier_required
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


@cashier_required
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


@cashier_required
def checkout(request):
    cart = request.session.get('cart', {})
    available_items = InventoryItem.objects.filter(quantity_in_stock__gt=0)
    recent_receipts = Receipt.objects.select_related('sale').order_by('-created_at')[:20]

    if not cart:
        return redirect('cashier')

    total = Decimal('0.00')

    for item_id, item in cart.items():
        total += Decimal(str(item['price'])) * item['quantity']

    if request.method == 'POST':
        cashier_name = request.POST.get('cashier_name', '').strip()
        payment_method = request.POST.get('payment_method', 'Cash').strip() or 'Cash'

        if not cashier_name:
            if request.user.is_authenticated:
                cashier_name = request.user.get_full_name() or request.user.get_username()
            else:
                cashier_name = 'Cashier'

        try:
            cash = Decimal(request.POST.get('cash', '0'))
        except (InvalidOperation, TypeError):
            return render(request, 'cashier/cashier_home.html', {
                'error': 'Please enter a valid payment amount.',
                'cash': '',
                'total': total,
                'change': 0,
                'items': available_items,
                'cart': cart,
                'recent_receipts': recent_receipts,
                'cashier_name': cashier_name,
                'payment_method': payment_method,
            })

        if cash < total and payment_method.lower() == 'cash':
            return render(request, 'cashier/cashier_home.html', {
                'error': 'Insufficient payment.',
                'cash': cash,
                'total': total,
                'change': 0,
                'items': available_items,
                'cart': cart,
                'recent_receipts': recent_receipts,
                'cashier_name': cashier_name,
                'payment_method': payment_method,
            })

        change = cash - total
        if change < 0:
            change = Decimal('0.00')

        # deduct stock and save the completed sale for reporting
        low_stock_alerts = []

        with transaction.atomic():
            inventory_items = {
                str(item.id): item
                for item in InventoryItem.objects.select_for_update().filter(id__in=cart.keys())
            }

            for item_id, item in cart.items():
                inventory_item = inventory_items.get(str(item_id))

                if not inventory_item or item['quantity'] > inventory_item.quantity_in_stock:
                    item_name = item.get('name', 'this item')
                    return render(request, 'cashier/cashier_home.html', {
                        'error': f'Not enough stock for {item_name}.',
                        'items': InventoryItem.objects.filter(quantity_in_stock__gt=0),
                        'cart': cart,
                        'total': total,
                        'recent_receipts': recent_receipts,
                        'cashier_name': cashier_name,
                        'payment_method': payment_method,
                    })

            sale = Sale.objects.create(
                total_amount=total,
                created_at=timezone.now()
            )

            for item_id, item in cart.items():
                inventory_item = inventory_items[str(item_id)]
                inventory_item.quantity_in_stock -= item['quantity']
                inventory_item.save(update_fields=['quantity_in_stock', 'status'])

                if inventory_item.quantity_in_stock <= inventory_item.minimum_stock_level:
                    low_stock_alerts.append(
                        f"{inventory_item.item_name} is low on stock ({inventory_item.quantity_in_stock} left)"
                    )

                SaleItem.objects.create(
                    sale=sale,
                    inventory_item=inventory_item,
                    item_name=item['name'],
                    quantity=item['quantity'],
                    price=Decimal(str(item['price']))
                )

            receipt = Receipt.objects.create(
                sale=sale,
                receipt_number=Receipt.generate_receipt_number(),
                cashier_name=cashier_name,
                payment_method=payment_method,
                cash_received=cash,
                change_amount=change,
            )

        # clear cart after successful transaction
        request.session['cart'] = {}

        return render(request, 'cashier/cashier_home.html', {
            'success': 'Transaction completed successfully.',
            'change': change,
            'cash': cash,
            'total': 0,
            'items': InventoryItem.objects.filter(quantity_in_stock__gt=0),
            'cart': {},
            'low_stock_alerts': low_stock_alerts,
            'receipt_id': receipt.id,
            'receipt_sale_id': sale.id,
            'receipt_number': receipt.receipt_number,
            'recent_receipts': Receipt.objects.select_related('sale').order_by('-created_at')[:20],
        })

    return redirect('cashier')


@admin_required
def receipt_history(request):
    """Display a paginated list of all receipts.
    Shows receipt number, sale date, total amount, and a link to view the
    individual receipt.
    """
    receipt_qs = Receipt.objects.select_related('sale').order_by('-created_at')
    search_query = request.GET.get('search', '').strip()
    cashier_filter = request.GET.get('cashier', '').strip()
    payment_filter = request.GET.get('payment_method', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    min_total = request.GET.get('min_total', '').strip()
    max_total = request.GET.get('max_total', '').strip()

    if search_query:
        receipt_qs = receipt_qs.filter(
            Q(receipt_number__icontains=search_query) |
            Q(cashier_name__icontains=search_query)
        )

    if cashier_filter:
        receipt_qs = receipt_qs.filter(cashier_name__icontains=cashier_filter)

    if payment_filter:
        receipt_qs = receipt_qs.filter(payment_method=payment_filter)

    if date_from:
        receipt_qs = receipt_qs.filter(created_at__date__gte=date_from)

    if date_to:
        receipt_qs = receipt_qs.filter(created_at__date__lte=date_to)

    try:
        if min_total:
            receipt_qs = receipt_qs.filter(sale__total_amount__gte=Decimal(min_total))
        if max_total:
            receipt_qs = receipt_qs.filter(sale__total_amount__lte=Decimal(max_total))
    except InvalidOperation:
        messages.error(request, 'Please enter valid amount filters.')

    payment_methods = Receipt.objects.exclude(payment_method='').values_list(
        'payment_method',
        flat=True,
    ).distinct().order_by('payment_method')
    # Pagination
    paginator = Paginator(receipt_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return render(request, 'cashier/receipt_history.html', {
        'page_obj': page_obj,
        'payment_methods': payment_methods,
        'query_params': query_params.urlencode(),
        'search_query': search_query,
        'cashier_filter': cashier_filter,
        'payment_filter': payment_filter,
        'date_from': date_from,
        'date_to': date_to,
        'min_total': min_total,
        'max_total': max_total,
    })


@admin_required
def void_receipt(request, receipt_id):
    """Void a receipt and its associated sale, and restore quantities of the items to stock."""
    if request.method == 'POST':
        receipt = get_object_or_404(Receipt, id=receipt_id)
        sale = receipt.sale
        
        if sale.is_voided:
            messages.warning(request, f'Receipt #{receipt.receipt_number} is already voided.')
            return redirect('receipt_history')
            
        with transaction.atomic():
            sale.is_voided = True
            sale.save(update_fields=['is_voided'])
            
            # Revert stock
            reverted_items = []
            for sale_item in sale.saleitem_set.all():
                inventory_item = sale_item.inventory_item
                if inventory_item is None:
                    continue

                inventory_item = InventoryItem.objects.select_for_update().get(pk=inventory_item.pk)
                inventory_item.quantity_in_stock += sale_item.quantity
                inventory_item.save()
                reverted_items.append(f"{sale_item.item_name} (+{sale_item.quantity})")
            
            messages.success(
                request, 
                f'Receipt #{receipt.receipt_number} has been voided. Restored stock: {", ".join(reverted_items)}.'
            )
    return redirect('receipt_history')


@admin_required
def daily_report(request, year=None, month=None, day=None):
    if year and month and day:
        report_date = date(year, month, day)
    else:
        report_date = now().date()

    sales = Sale.objects.filter(
        created_at__date=report_date
    ).order_by('-created_at')

    active_sales = sales.filter(is_voided=False)
    total = active_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get all sale items for the report date (excluding voided sales)
    sale_items = SaleItem.objects.filter(
        sale__created_at__date=report_date,
        sale__is_voided=False
    )
    
    # Total items sold (sum of quantities)
    total_items_sold = sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Best-selling items for the day
    best_sellers = sale_items.values('item_name').annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-total_qty')[:5]
    
    # All items sold today with quantities
    items_sold = sale_items.values('item_name').annotate(
        total_qty=Sum('quantity'),
        unit_price=F('price'),
        total_revenue=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
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
        'sales': sales, # keep all sales for audit logs
        'total': total,
        'report_date': report_date,
        'is_monitor': get_request_role(request) == 'monitor',
        'can_modify_reports': get_request_role(request) != 'monitor',
        'transaction_count': active_sales.count(),
        'total_items_sold': total_items_sold,
        'best_sellers': best_sellers,
        'items_sold': items_sold,
        'low_stock_items': low_stock_items,
        'fast_moving_items': fast_moving_items,
    })


@admin_required
def monthly_report(request, year=None, month=None):
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

    active_sales = sales.filter(is_voided=False)
    total = active_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get all sale items for the month
    sale_items = SaleItem.objects.filter(
        sale__created_at__year=report_year,
        sale__created_at__month=report_month,
        sale__is_voided=False
    )
    
    # Total items sold for the month
    total_items_sold = sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Top-selling items of the month
    best_sellers = sale_items.values('item_name').annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('-total_qty')[:5]
    
    # Lowest-selling items
    lowest_sellers = sale_items.values('item_name').annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
    ).order_by('total_qty')[:5]
    
    # Daily sales summary
    from inventory.models import RestockHistory
    daily_sales = sale_items.values('sale__created_at__date').annotate(
        daily_qty=Sum('quantity'),
        daily_revenue=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
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
        restock_count=models.Count('id'),
        total_qty_added=Sum('quantity_added')
    ).order_by('-restock_count')[:5]

    month_name = datetime(report_year, report_month, 1).strftime('%B')
    
    return render(request, 'report/monthly.html', {
        'sales': sales, # keep all sales for audit logs
        'total': total,
        'month': report_month,
        'year': report_year,
        'month_name': month_name,
        'is_monitor': get_request_role(request) == 'monitor',
        'can_modify_reports': get_request_role(request) != 'monitor',
        'transaction_count': active_sales.count(),
        'total_items_sold': total_items_sold,
        'best_sellers': best_sellers,
        'lowest_sellers': lowest_sellers,
        'daily_sales': daily_sales,
        'low_stock_items': low_stock_items,
        'total_restocks_count': total_restocks_count,
        'total_quantity_restocked': total_quantity_restocked,
    })


@admin_required
def void_daily_report(request):
    """Void all active sales records for today and restore stock."""
    if request.method == 'POST':
        today = now().date()
        sales_to_void = Sale.objects.filter(created_at__date=today, is_voided=False)
        count = 0
        with transaction.atomic():
            for sale in sales_to_void:
                sale.is_voided = True
                sale.save(update_fields=['is_voided'])
                for sale_item in sale.saleitem_set.all():
                    inventory_item = sale_item.inventory_item
                    if inventory_item is None:
                        continue
                    inventory_item = InventoryItem.objects.select_for_update().get(pk=inventory_item.pk)
                    inventory_item.quantity_in_stock += sale_item.quantity
                    inventory_item.save()
                count += 1
        
        messages.success(request, f'Successfully voided {count} sales records for today and restored stock.')
    return redirect('daily_report')


@admin_required
def void_monthly_report(request):
    """Void all active sales records for the current month and restore stock."""
    if request.method == 'POST':
        today = now()
        current_month = today.month
        current_year = today.year
        
        sales_to_void = Sale.objects.filter(
            created_at__year=current_year,
            created_at__month=current_month,
            is_voided=False
        )
        count = 0
        with transaction.atomic():
            for sale in sales_to_void:
                sale.is_voided = True
                sale.save(update_fields=['is_voided'])
                for sale_item in sale.saleitem_set.all():
                    inventory_item = sale_item.inventory_item
                    if inventory_item is None:
                        continue
                    inventory_item = InventoryItem.objects.select_for_update().get(pk=inventory_item.pk)
                    inventory_item.quantity_in_stock += sale_item.quantity
                    inventory_item.save()
                count += 1
        
        messages.success(request, f'Successfully voided {count} sales records for {today.strftime("%B %Y")} and restored stock.')
    return redirect('monthly_report')


@admin_required
def daily_report_history(request):
    from django.db.models.functions import TruncDate
    from django.db.models import Count

    daily_history_qs = Sale.objects.filter(is_voided=False).annotate(
        report_date=TruncDate('created_at')
    ).values('report_date').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_date')[:30]

    daily_history = list(daily_history_qs)

    return render(request, 'report/daily_report_history.html', {
        'daily_history': daily_history,
    })


@admin_required
def monthly_report_history(request):
    from django.db.models.functions import TruncMonth
    from django.db.models import Count

    monthly_history_qs = Sale.objects.filter(is_voided=False).annotate(
        report_month=TruncMonth('created_at')
    ).values('report_month').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_month')[:12]

    monthly_history = list(monthly_history_qs)

    return render(request, 'report/monthly_report_history.html', {
        'monthly_history': monthly_history,
    })


@admin_required
def report_history(request):
    from django.db.models.functions import TruncDate, TruncMonth
    from django.db.models import Count

    active_sales = Sale.objects.filter(is_voided=False)

    daily_history = active_sales.annotate(
        report_date=TruncDate('created_at')
    ).values('report_date').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_date')[:30]

    monthly_history = active_sales.annotate(
        report_month=TruncMonth('created_at')
    ).values('report_month').annotate(
        transaction_count=Count('id'),
        total_revenue=Sum('total_amount')
    ).order_by('-report_month')[:12]

    return render(request, 'report/report_history.html', {
        'daily_history': daily_history,
        'monthly_history': monthly_history,
    })


@login_required
def generate_receipt(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    
    # Check if receipt already exists
    if hasattr(sale, 'receipt'):
        receipt = sale.receipt
    else:
        with transaction.atomic():
            receipt = Receipt.objects.create(
                sale=sale,
                receipt_number=Receipt.generate_receipt_number(),
                cashier_name='Cashier',
                payment_method='Cash',
                cash_received=sale.total_amount,
                change_amount=0,
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


@login_required
def monitor_dashboard(request):
    """Unified, read-only Monitor Dashboard showcasing Cashier stock levels and Admin metrics side-by-side."""
    # Restrict Cashiers from accessing
    role = 'cashier'
    if hasattr(request.user, 'profile'):
        role = request.user.profile.role
        
    if role == 'cashier' and not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, "Permission Denied: Cashiers cannot access the Monitor Desk.")
        return redirect('cashier')

    # 1. Cashier Side Data
    items = InventoryItem.objects.all().order_by('item_name')

    # 2. Admin Side Data
    from inventory.models import RestockHistory
    total_items = InventoryItem.objects.count()
    low_stock_count = InventoryItem.objects.filter(
        quantity_in_stock__lte=F('minimum_stock_level'), 
        quantity_in_stock__gt=0
    ).count()
    out_of_stock_count = InventoryItem.objects.filter(quantity_in_stock=0).count()

    today = now().date()
    today_sales = Sale.objects.filter(created_at__date=today, is_voided=False)
    today_revenue = today_sales.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    transaction_count = today_sales.count()

    recent_receipts = Receipt.objects.select_related('sale').order_by('-created_at')[:10]
    recent_restocks = RestockHistory.objects.select_related('inventory_item').order_by('-created_at')[:5]

    return render(request, 'report/monitor_dashboard.html', {
        'items': items,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'today_revenue': today_revenue,
        'transaction_count': transaction_count,
        'recent_receipts': recent_receipts,
        'recent_restocks': recent_restocks,
        'report_date': today,
    })

