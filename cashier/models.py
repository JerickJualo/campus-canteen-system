from django.db import models

from inventory.models import InventoryItem


class Transaction(models.Model):
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction #{self.id}"


class TransactionItem(models.Model):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item = models.ForeignKey('inventory.InventoryItem', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.item.item_name
    
class Sale(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_voided = models.BooleanField(default=False)

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=100)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)



class Order(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"Order {self.id}"


class Receipt(models.Model):
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='receipt')
    receipt_number = models.CharField(max_length=20, unique=True)
    cashier_name = models.CharField(max_length=100, default='Cashier')
    payment_method = models.CharField(max_length=50, default='Cash')
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Receipt #{self.receipt_number}"
    
    @classmethod
    def generate_receipt_number(cls):
        from django.utils import timezone
        today = timezone.now().strftime('%Y%m%d')
        last_receipt = cls.objects.filter(receipt_number__startswith=f'R{today}').order_by('receipt_number').last()
        
        if last_receipt:
            last_number = int(last_receipt.receipt_number[9:])
            new_number = last_number + 1
        else:
            new_number = 1
            
        return f'R{today}{new_number:04d}'
