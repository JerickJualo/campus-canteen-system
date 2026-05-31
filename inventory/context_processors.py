from django.db.models import F

from .models import InventoryItem


def stock_alerts(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}

    low_stock_count = InventoryItem.objects.filter(
        quantity_in_stock__lte=F('minimum_stock_level'),
        quantity_in_stock__gt=0,
    ).count()
    out_of_stock_count = InventoryItem.objects.filter(quantity_in_stock=0).count()

    return {
        'global_low_stock_count': low_stock_count,
        'global_out_of_stock_count': out_of_stock_count,
        'global_stock_alert_count': low_stock_count + out_of_stock_count,
    }
