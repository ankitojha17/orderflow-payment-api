from django.db import models
from services.models.order import Order


class Payment(models.Model):
    """Tracks the Razorpay payment lifecycle for a single Order."""

    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    is_webhook_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment'

    def __str__(self):
        return f"Payment for Order #{self.order_id} ({self.status})"
