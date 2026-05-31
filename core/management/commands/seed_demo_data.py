from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from cashier.models import CashierShift, Receipt, Sale, SaleItem
from core.management.commands.clear_demo_data import DEMO_ITEM_NAMES, clear_demo_data
from core.models import ActivityLog
from inventory.models import Category, InventoryItem, RestockHistory


PASSWORD = 'demo12345'

ITEMS = [
    ('Chicken Pastil', 'Dish', '55.00', 42, 12),
    ('Pork Siomai Rice', 'Dish', '60.00', 35, 10),
    ('Burger Steak Rice', 'Dish', '75.00', 24, 8),
    ('Fried Chicken Rice', 'Dish', '85.00', 18, 8),
    ('Tuna Sandwich', 'Snacks', '35.00', 28, 10),
    ('Egg Sandwich', 'Snacks', '30.00', 22, 10),
    ('Pancit Canton', 'Noodles', '35.00', 7, 10),
    ('Cup Noodles Beef', 'Noodles', '45.00', 0, 8),
    ('Cup Noodles Chicken', 'Noodles', '45.00', 14, 8),
    ('Bottled Water 500ml', 'Drinks', '20.00', 65, 20),
    ('Iced Tea', 'Drinks', '25.00', 8, 15),
    ('C2 Green Tea', 'Drinks', '30.00', 30, 12),
    ('Royal Tru-Orange', 'Drinks', '25.00', 4, 12),
    ('Coke Mismo', 'Drinks', '25.00', 26, 12),
    ('Mango Juice', 'Drinks', '30.00', 17, 12),
    ('Banana Cue', 'Snacks', '15.00', 31, 10),
    ('Turon', 'Snacks', '15.00', 12, 10),
    ('Cheese Bread', 'Snacks', '20.00', 9, 15),
    ('Chocolate Crinkles', 'Snacks', '12.00', 44, 15),
    ('Piattos', 'Snacks', '22.00', 21, 10),
    ('Nova', 'Snacks', '22.00', 16, 10),
    ('SkyFlakes', 'Snacks', '10.00', 52, 20),
    ('Peanut Bar', 'Snacks', '8.00', 38, 15),
    ('Choco Mucho', 'Snacks', '18.00', 23, 10),
    ('Ballpen Black', 'Others', '12.00', 25, 10),
    ('Yellow Pad', 'Others', '38.00', 6, 10),
    ('Bond Paper Short', 'Others', '2.00', 95, 30),
    ('Plastic Spoon', 'Others', '1.00', 120, 30),
]

SALE_PATTERNS = [
    (0, 'morning', 'Cash', [('Chicken Pastil', 3), ('Bottled Water 500ml', 3), ('Turon', 2)]),
    (0, 'morning', 'GCash', [('Pork Siomai Rice', 2), ('Iced Tea', 2)]),
    (0, 'afternoon', 'Cash', [('Fried Chicken Rice', 2), ('Coke Mismo', 2), ('Piattos', 1)]),
    (0, 'afternoon', 'Maya', [('Tuna Sandwich', 3), ('Mango Juice', 3)]),
    (1, 'morning', 'Cash', [('Burger Steak Rice', 2), ('Bottled Water 500ml', 2)]),
    (1, 'afternoon', 'GCash', [('Pancit Canton', 4), ('Royal Tru-Orange', 4)]),
    (2, 'morning', 'Cash', [('Chicken Pastil', 5), ('SkyFlakes', 3)]),
    (3, 'afternoon', 'Card', [('Fried Chicken Rice', 1), ('C2 Green Tea', 1), ('Choco Mucho', 2)]),
    (5, 'morning', 'GCash', [('Pork Siomai Rice', 3), ('Banana Cue', 3)]),
    (7, 'afternoon', 'Cash', [('Egg Sandwich', 4), ('Mango Juice', 2)]),
    (10, 'morning', 'Maya', [('Chicken Pastil', 2), ('Coke Mismo', 2)]),
    (14, 'afternoon', 'Cash', [('Burger Steak Rice', 3), ('Iced Tea', 3)]),
    (18, 'morning', 'GCash', [('Tuna Sandwich', 2), ('Chocolate Crinkles', 5)]),
    (24, 'afternoon', 'Cash', [('Fried Chicken Rice', 2), ('Bottled Water 500ml', 2)]),
    (32, 'morning', 'Cash', [('Pork Siomai Rice', 2), ('Nova', 2)]),
    (38, 'afternoon', 'GCash', [('Chicken Pastil', 4), ('C2 Green Tea', 4)]),
    (45, 'morning', 'Card', [('Egg Sandwich', 3), ('Choco Mucho', 3)]),
    (52, 'afternoon', 'Cash', [('Pancit Canton', 2), ('Royal Tru-Orange', 2)]),
]

VOID_INDICES = {3: 'Customer changed order before claiming.', 11: 'Duplicate entry during peak hour.'}


def set_created_at(obj, created_at):
    obj.created_at = created_at
    obj.save(update_fields=['created_at'])


def make_user(username, role, is_staff=False, is_superuser=False):
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            'email': f'{username}@demo.local',
            'is_staff': is_staff,
            'is_superuser': is_superuser,
            'is_active': True,
        },
    )
    user.email = f'{username}@demo.local'
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.is_active = True
    user.set_password(PASSWORD)
    user.save()

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.save()
    return user


def log(user, action_type, description, target, created_at):
    entry = ActivityLog.objects.create(
        user=user,
        action_type=action_type,
        description=f'[DEMO] {description}'[:255],
        target=target[:120],
    )
    set_created_at(entry, created_at)
    return entry


class Command(BaseCommand):
    help = 'Seed realistic presentation data for the campus canteen system.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-existing-demo',
            action='store_true',
            help='Do not clear previously seeded demo data before inserting.',
        )

    def handle(self, *args, **options):
        if not options['keep_existing_demo']:
            counts = clear_demo_data()
            self.stdout.write(
                f"Cleared old demo data: {counts['sales']} sales, {counts['items']} items, {counts['users']} users."
            )

        now = timezone.now()

        with transaction.atomic():
            admin = make_user('demo_admin', 'admin', is_staff=True, is_superuser=True)
            cashier_morning = make_user('demo_cashier_morning', 'cashier')
            cashier_afternoon = make_user('demo_cashier_afternoon', 'cashier')
            monitor = make_user('demo_monitor', 'monitor')

            for category in ['Dish', 'Snacks', 'Noodles', 'Drinks', 'Others']:
                Category.objects.get_or_create(name=category)

            items = {}
            for name, category, price, stock, minimum in ITEMS:
                item, _ = InventoryItem.objects.update_or_create(
                    item_name=name,
                    defaults={
                        'category': category,
                        'unit_price': Decimal(price),
                        'quantity_in_stock': stock,
                        'minimum_stock_level': minimum,
                    },
                )
                items[name] = item

            restock_specs = [
                ('Bottled Water 500ml', 80, 18),
                ('Chicken Pastil', 50, 15),
                ('Pork Siomai Rice', 45, 12),
                ('Iced Tea', 35, 6),
                ('Royal Tru-Orange', 24, 2),
                ('Yellow Pad', 20, 3),
                ('Cup Noodles Chicken', 30, 4),
                ('Chocolate Crinkles', 60, 20),
            ]
            for idx, (item_name, added, previous) in enumerate(restock_specs):
                item = items[item_name]
                created_at = now - timedelta(days=idx * 4 + 1, hours=2)
                record = RestockHistory.objects.create(
                    inventory_item=item,
                    quantity_added=added,
                    previous_quantity=previous,
                    new_quantity=previous + added,
                    restocked_by=admin,
                    note='[DEMO] Supplier delivery before class rush',
                )
                set_created_at(record, created_at)
                log(admin, 'restock', f'Restocked {item_name}: {previous} to {previous + added}', item_name, created_at)

            shifts = {}
            for days_back in sorted({pattern[0] for pattern in SALE_PATTERNS}):
                for label, user, name, start_hour in [
                    ('morning', cashier_morning, 'Demo Cashier Morning', 7),
                    ('afternoon', cashier_afternoon, 'Demo Cashier Afternoon', 13),
                ]:
                    started_at = (now - timedelta(days=days_back)).replace(
                        hour=start_hour,
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                    ended_at = started_at + timedelta(hours=5)
                    shift = CashierShift.objects.create(
                        cashier=user,
                        cashier_name=name,
                        started_at=started_at,
                        ended_at=ended_at,
                        opening_note='[DEMO] Presentation shift',
                        closing_note='[DEMO] Shift balanced for demo',
                    )
                    shifts[(days_back, label)] = shift
                    log(user, 'shift', f'Completed {label} shift for {name}', name, ended_at)

            for idx, (days_back, shift_label, payment_method, line_items) in enumerate(SALE_PATTERNS, start=1):
                shift = shifts[(days_back, shift_label)]
                created_at = shift.started_at + timedelta(minutes=22 + (idx % 7) * 18)
                total = sum(items[name].unit_price * qty for name, qty in line_items)
                is_voided = idx in VOID_INDICES
                sale = Sale.objects.create(
                    total_amount=total,
                    is_voided=is_voided,
                    void_reason=VOID_INDICES.get(idx, ''),
                    voided_at=created_at + timedelta(minutes=12) if is_voided else None,
                    voided_by=admin if is_voided else None,
                    shift=shift,
                )
                set_created_at(sale, created_at)

                for item_name, qty in line_items:
                    SaleItem.objects.create(
                        sale=sale,
                        inventory_item=items[item_name],
                        item_name=item_name,
                        quantity=qty,
                        price=items[item_name].unit_price,
                    )

                cash_received = total
                if payment_method == 'Cash':
                    cash_received = total + Decimal('100.00')

                receipt = Receipt.objects.create(
                    sale=sale,
                    receipt_number=f'DMO{created_at:%Y%m%d}{idx:04d}',
                    cashier_name=shift.cashier_name,
                    payment_method=payment_method,
                    cash_received=cash_received,
                    change_amount=max(cash_received - total, Decimal('0.00')),
                )
                set_created_at(receipt, created_at)

                log(
                    shift.cashier,
                    'checkout',
                    f'Completed receipt #{receipt.receipt_number} via {payment_method} for PHP {total}',
                    receipt.receipt_number,
                    created_at,
                )
                if is_voided:
                    log(
                        admin,
                        'void',
                        f'Voided receipt #{receipt.receipt_number}: {sale.void_reason}',
                        receipt.receipt_number,
                        sale.voided_at,
                    )

            log(admin, 'user', "Created demo cashier and monitor accounts", 'demo accounts', now - timedelta(days=1))
            log(admin, 'inventory', f'Prepared {len(DEMO_ITEM_NAMES)} presentation inventory items', 'demo inventory', now)
            log(monitor, 'user', 'Reviewed dashboard in monitor mode', 'monitor dashboard', now - timedelta(hours=1))

        self.stdout.write(self.style.SUCCESS(
            'Demo data seeded successfully.\n'
            f'Accounts: demo_admin, demo_cashier_morning, demo_cashier_afternoon, demo_monitor\n'
            f'Password for all demo accounts: {PASSWORD}'
        ))
