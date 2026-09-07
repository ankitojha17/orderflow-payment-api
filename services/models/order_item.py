from django.db import models
from services.models.order import Order
from services.models.product import Product


class OrderItem(models.Model):
    """A single product line within an Order, price snapshotted at purchase time."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'order_item'

    def __str__(self):
        return f"{self.quantity} x {self.product.name} (Order #{self.order_id})"
