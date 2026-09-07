from django.core.management.base import BaseCommand

from services.models import Order, Payment
from services.tasks import send_order_confirmation_email_task


class Command(BaseCommand):
    """
    Safety-net command: queues confirmation emails for any payment marked
    successful whose is_webhook_processed flag never got set (e.g. an order
    manually marked paid via /admin/). Safe to run repeatedly — idempotent
    by construction, since it only targets is_webhook_processed=False rows
    and flips the flag once queued.
    """
    help = "Queues confirmation emails for paid orders the webhook may have missed."

    def handle(self, *args, **options):
        missed_payments = Payment.objects.select_related('order__user').filter(
            status=Payment.Status.SUCCESS,
            order__status=Order.Status.PAID,
            is_webhook_processed=False,
        )

        count = 0
        for payment in missed_payments:
            send_order_confirmation_email_task.delay(payment.order.user.email, payment.order.id)
            payment.is_webhook_processed = True
            payment.save(update_fields=['is_webhook_processed'])
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Queued {count} confirmation email(s)."))
