from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal

from inventory.models import InventoryItem
from cashier.models import Sale, SaleItem, Receipt


class CanteenSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Seed default test users
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@campus.edu',
            password='admin123'
        )
        self.cashier_user = User.objects.create_user(
            username='cashier',
            email='cashier@campus.edu',
            password='cashier123'
        )
        # Create a test inventory item
        self.test_item = InventoryItem.objects.create(
            item_name="Spam and Rice",
            category="Dish",
            unit_price=Decimal("75.00"),
            quantity_in_stock=10,
            minimum_stock_level=3
        )

    def test_unauthenticated_redirect(self):
        """Unauthenticated requests should redirect to the login page."""
        response = self.client.get(reverse('cashier'))
        self.assertRedirects(response, '/accounts/login/?next=/cashier/')

        response = self.client.get(reverse('inventory_dashboard'))
        self.assertRedirects(response, '/accounts/login/?next=/inventory/')

    def test_cashier_access_restrictions(self):
        """Cashier users should access the cashier counter but be blocked from inventory/reports."""
        self.client.login(username='cashier', password='cashier123')
        
        # Access cashier: Allowed (200 OK)
        response = self.client.get(reverse('cashier'))
        self.assertEqual(response.status_code, 200)

        # Access inventory: Redirected to cashier panel with permission error
        response = self.client.get(reverse('inventory_dashboard'))
        self.assertRedirects(response, reverse('cashier'))
        
        # Access daily report: Redirected to cashier panel
        response = self.client.get(reverse('daily_report'))
        self.assertRedirects(response, reverse('cashier'))

    def test_admin_full_access(self):
        """Admin users should have access to inventory, reports, and the cashier counter."""
        self.client.login(username='admin', password='admin123')

        # Access inventory dashboard
        response = self.client.get(reverse('inventory_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Access daily report
        response = self.client.get(reverse('daily_report'))
        self.assertEqual(response.status_code, 200)

        # Access cashier: Allowed
        response = self.client.get(reverse('cashier'))
        self.assertEqual(response.status_code, 200)

    def test_checkout_and_void_flow(self):
        """Test transaction checkout, stock deduction, void logic, and stock restoration."""
        self.client.login(username='cashier', password='cashier123')

        # Setup cart session
        session = self.client.session
        session['cart'] = {
            str(self.test_item.id): {
                'name': self.test_item.item_name,
                'price': float(self.test_item.unit_price),
                'quantity': 2
            }
        }
        session.save()

        # Checkout
        response = self.client.post(reverse('checkout'), {
            'cashier_name': 'Test Cashier',
            'payment_method': 'Cash',
            'cash': '200.00'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Transaction completed successfully.', response.content.decode())

        # Verify stock decremented
        self.test_item.refresh_from_db()
        self.assertEqual(self.test_item.quantity_in_stock, 8)

        # Verify sale and receipt created
        sale = Sale.objects.latest('id')
        receipt = Receipt.objects.get(sale=sale)
        self.assertEqual(sale.total_amount, Decimal('150.00'))
        self.assertEqual(sale.is_voided, False)
        self.assertIsNotNone(sale.shift)
        self.assertEqual(receipt.receipt_number.startswith('R'), True)

        # Log in as Admin to void the receipt
        self.client.logout()
        self.client.login(username='admin', password='admin123')

        # Void transaction
        response = self.client.post(reverse('void_receipt', args=[receipt.id]), {
            'void_reason': 'Customer returned order'
        })
        self.assertRedirects(response, reverse('receipt_history'))

        # Verify sale is marked voided
        sale.refresh_from_db()
        self.assertEqual(sale.is_voided, True)
        self.assertEqual(sale.void_reason, 'Customer returned order')

        # Verify stock restored
        self.test_item.refresh_from_db()
        self.assertEqual(self.test_item.quantity_in_stock, 10)

        # Verify daily report sum ignores voided sales
        response = self.client.get(reverse('daily_report'))
        self.assertEqual(response.context['total'], Decimal('0.00'))
        self.assertEqual(response.context['transaction_count'], 0)


class MonitorRoleTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Seed Admin
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@campus.edu',
            password='admin123'
        )
        # Create a Monitor user
        self.monitor_user = User.objects.create_user(
            username='monitor',
            email='monitor@campus.edu',
            password='monitor123'
        )
        # Assign role
        self.monitor_user.profile.role = 'monitor'
        self.monitor_user.profile.save()

    def test_monitor_dashboard_access(self):
        """Monitor dashboard should be accessible to monitor and admin roles but blocked for cashiers."""
        # Unauthenticated: Redirects to login
        response = self.client.get(reverse('monitor_dashboard'))
        self.assertEqual(response.status_code, 302)

        # Monitor: Allowed (200 OK)
        self.client.login(username='monitor', password='monitor123')
        response = self.client.get(reverse('monitor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Admin: Allowed (200 OK)
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('monitor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Cashier: Redirected to cashiercounter
        cashier_user = User.objects.create_user(
            username='cashier_test',
            password='password123'
        )
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get(reverse('monitor_dashboard'))
        self.assertRedirects(response, reverse('cashier'))

    def test_monitor_read_only_access(self):
        """Monitor users should view approved inventory and report pages only."""
        self.client.login(username='monitor', password='monitor123')

        response = self.client.get(reverse('inventory_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Add Item')
        self.assertNotContains(response, 'Multi-item Restock')

        response = self.client.get(reverse('inventory_history'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('daily_report'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('monthly_report'))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('cashier'))
        self.assertRedirects(response, reverse('monitor_dashboard'))

    def test_monitor_modification_blocks(self):
        """Monitor users trying to post changes to checkout or restocks should be blocked and redirected."""
        self.client.login(username='monitor', password='monitor123')

        # POST to checkout
        response = self.client.post(reverse('checkout'), {
            'cashier_name': 'Monitor',
            'payment_method': 'Cash',
            'cash': '100.00'
        })
        self.assertRedirects(response, reverse('monitor_dashboard'))

        response = self.client.post(reverse('add_inventory_item'), {
            'item_name': 'Blocked Item',
            'category': 'Dish',
            'unit_price': '10.00',
            'quantity_in_stock': '5',
            'minimum_stock_level': '1',
        })
        self.assertRedirects(response, reverse('monitor_dashboard'))

        response = self.client.post(reverse('void_daily_report'))
        self.assertRedirects(response, reverse('monitor_dashboard'))

