from decimal import Decimal

from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError

from services.models import Order, OrderItem, Product
from services.serializer import CreateOrderSerializer, OrderSerializer
from services.utils.authentication import Authentication
from services.utils.response_handler import ResponseHandler
from services.constants import messages


class CreateOrderView(Authentication, generics.CreateAPIView):
    """
    Requires a valid JWT. The serializer only validates input shape and does
    a friendly stock pre-check; the actual order creation — including the
    authoritative, race-condition-safe stock check — happens here.
    """
    serializer_class = CreateOrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = self._create_order(request.auth_user, serializer.validated_data['items'])

        return ResponseHandler(
            message=messages.ORDER_CREATED,
            data=OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    def _create_order(self, user, items_data):
        """
        select_for_update() locks each Product row for the duration of this
        transaction, so two concurrent requests for the same product can't
        both read the same stock_quantity and oversell it. The second request
        blocks until the first commits, then re-reads the updated stock.
        """
        order = Order.objects.create(user=user, total_amount=0)
        total = Decimal('0.00')

        for item in items_data:
            product = Product.objects.select_for_update().get(id=item['product_id'])

            # Negative case first: stock may have changed since the serializer's
            # pre-check (another request could have bought it in between).
            if product.stock_quantity < item['quantity']:
                raise ValidationError(f"Insufficient stock for {product.name}.")

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item['quantity'],
                price_at_purchase=product.price,
            )
            product.stock_quantity -= item['quantity']
            product.save(update_fields=['stock_quantity'])
            total += product.price * item['quantity']

        order.total_amount = total
        order.save(update_fields=['total_amount'])
        return order
