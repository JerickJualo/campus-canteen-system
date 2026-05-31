from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cashier.models import CashierShift, Receipt, Sale
from core.models import ActivityLog
from inventory.models import InventoryItem, RestockHistory


DEMO_USERNAMES = [
    'demo_admin',
    'demo_cashier_morning',
    'demo_cashier_afternoon',
    'demo_monitor',
]

DEMO_ITEM_NAMES = [
    'Chicken Pastil',
    'Pork Siomai Rice',
    'Burger Steak Rice',
    'Fried Chicken Rice',
    'Tuna Sandwich',
    'Egg Sandwich',
    'Pancit Canton',
    'Cup Noodles Beef',
    'Cup Noodles Chicken',
    'Bottled Water 500ml',
    'Iced Tea',
    'C2 Green Tea',
    'Royal Tru-Orange',
    'Coke Mismo',
    'Mango Juice',
    'Banana Cue',
    'Turon',
    'Cheese Bread',
    'Chocolate Crinkles',
    'Piattos',
    'Nova',
    'SkyFlakes',
    'Peanut Bar',
    'Choco Mucho',
    'Ballpen Black',
    'Yellow Pad',
    'Bond Paper Short',
    'Plastic Spoon',
]


def clear_demo_data():
    with transaction.atomic():
        demo_sales = Sale.objects.filter(receipt__receipt_number__startswith='DMO')
        deleted_sales = demo_sales.count()
        demo_sales.delete()

        deleted_shifts, _ = CashierShift.objects.filter(
            opening_note__startswith='[DEMO]'
        ).delete()

        deleted_restocks, _ = RestockHistory.objects.filter(
            note__startswith='[DEMO]'
        ).delete()

        deleted_logs, _ = ActivityLog.objects.filter(
            description__startswith='[DEMO]'
        ).delete()

        deleted_items, _ = InventoryItem.objects.filter(
            item_name__in=DEMO_ITEM_NAMES
        ).delete()

        deleted_users, _ = User.objects.filter(
            username__in=DEMO_USERNAMES
        ).delete()

    return {
        'sales': deleted_sales,
        'shifts': deleted_shifts,
        'restocks': deleted_restocks,
        'logs': deleted_logs,
        'items': deleted_items,
        'users': deleted_users,
    }


class Command(BaseCommand):
    help = 'Remove presentation demo data created by seed_demo_data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Confirm deletion of demo data without prompting.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            raise CommandError('This removes demo records. Re-run with --yes to confirm.')

        counts = clear_demo_data()
        self.stdout.write(self.style.SUCCESS(
            'Demo data cleared: '
            f"{counts['sales']} sales, "
            f"{counts['shifts']} shifts, "
            f"{counts['restocks']} restocks, "
            f"{counts['logs']} activity logs, "
            f"{counts['items']} items, "
            f"{counts['users']} users."
        ))
