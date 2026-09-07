from rest_framework import generics, status
from django.db import transaction

from services.models import Order, Payment
from services.utils.authentication import Authentication
from services.utils.razorpay_client import get_razorpay_client
from services.utils.response_handler import ResponseHandler
from services.constants import messages


class CreatePaymentView(Authentication, generics.CreateAPIView):
    """Requires a valid JWT. Creates a Razorpay order for an existing Order."""

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            # select_for_update locks this Order row for the transaction, so
            # two near-simultaneous POSTs to /pay/ for the same order can't
            # both read status=pending and both create a Razorpay order —
            # the second request blocks until the first commits its Payment
            # row, then re-reads the (now updated) state.
            order = (
                Order.objects.select_for_update()
                .filter(id=kwargs['order_id'], user=request.auth_user, is_deleted=False)
                .first()
            )

            # Negative cases first.
            if not order:
                return ResponseHandler(success=False, message=messages.ORDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

            if order.status == Order.Status.PAID:
                return ResponseHandler(success=False, message=messages.ORDER_ALREADY_PAID, status=status.HTTP_409_CONFLICT)

            if order.total_amount <= 0:
                return ResponseHandler(success=False, message=messages.INVALID_ORDER_AMOUNT, status=status.HTTP_400_BAD_REQUEST)

            # A Payment row may already exist from a prior, uncompleted attempt
            # (e.g. user abandoned checkout on Razorpay's page, or a previous
            # attempt failed). Reuse/reset it instead of silently creating a
            # second Razorpay order for the same Order.
            existing_payment = Payment.objects.select_for_update().filter(order=order).first()
            if existing_payment and existing_payment.status == Payment.Status.SUCCESS:
                return ResponseHandler(success=False, message=messages.ORDER_ALREADY_PAID, status=status.HTTP_409_CONFLICT)

            client = get_razorpay_client()
            # Trade-off, worth knowing for an interview: this call happens
            # while still holding the Order row lock from select_for_update()
            # above, so the lock is held for the duration of a network round
            # trip to Razorpay rather than just a DB write. For this project's
            # traffic level that's an acceptable simplification — the
            # alternative (release the lock, call Razorpay, re-acquire and
            # re-check) is more correct under high concurrency but adds
            # complexity this project doesn't need yet.
            razorpay_order = client.order.create({
                'amount': int(order.total_amount * 100),  # Razorpay expects paise
                'currency': 'INR',
                'receipt': f'order_{order.id}',
            })

            # Reset the full payment state on every new attempt, not just the
            # razorpay_order_id. Without this, a payment that FAILED (or any
            # stale is_webhook_processed=True) would survive into the new
            # attempt, and the webhook's idempotency guard would then silently
            # ignore the *next* legitimate payment.captured event for this order.
            Payment.objects.update_or_create(
                order=order,
                defaults={
                    'razorpay_order_id': razorpay_order['id'],
                    'razorpay_payment_id': '',
                    'status': Payment.Status.CREATED,
                    'is_webhook_processed': False,
                },
            )

            return ResponseHandler(
                message=messages.PAYMENT_INITIATED,
                data={
                    'razorpay_order_id': razorpay_order['id'],
                    'amount': razorpay_order['amount'],
                    'currency': razorpay_order['currency'],
                },
                status=status.HTTP_201_CREATED,
            )
