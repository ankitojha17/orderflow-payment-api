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
            order = (
                Order.objects.select_for_update()
                .filter(id=kwargs['order_id'], user=request.auth_user, is_deleted=False)
                .first()
            )

            if not order:
                return ResponseHandler(success=False, message=messages.ORDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

            if order.status == Order.Status.PAID:
                return ResponseHandler(success=False, message=messages.ORDER_ALREADY_PAID, status=status.HTTP_409_CONFLICT)

            if order.total_amount <= 0:
                return ResponseHandler(success=False, message=messages.INVALID_ORDER_AMOUNT, status=status.HTTP_400_BAD_REQUEST)

            existing_payment = Payment.objects.select_for_update().filter(order=order).first()
            if existing_payment and existing_payment.status == Payment.Status.SUCCESS:
                return ResponseHandler(success=False, message=messages.ORDER_ALREADY_PAID, status=status.HTTP_409_CONFLICT)

            client = get_razorpay_client()
            razorpay_order = client.order.create({
                'amount': int(order.total_amount * 100),
                'currency': 'INR',
                'receipt': f'order_{order.id}',
            })

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
