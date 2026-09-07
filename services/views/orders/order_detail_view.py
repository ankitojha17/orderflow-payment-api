from rest_framework import generics, status

from services.models import Order
from services.serializer import OrderSerializer
from services.utils.authentication import Authentication
from services.utils.response_handler import ResponseHandler
from services.constants import messages


class OrderDetailView(Authentication, generics.RetrieveAPIView):
    """
    Requires a valid JWT. select_related('user') avoids a second query for
    the owner check; prefetch_related('items__product') avoids one query
    per order item when the serializer reads item.product.name.
    """
    serializer_class = OrderSerializer

    def retrieve(self, request, *args, **kwargs):
        order = (
            Order.objects.select_related('user')
            .prefetch_related('items__product')
            .filter(id=kwargs['pk'], user=request.auth_user, is_deleted=False)
            .first()
        )

        # Negative case first.
        if not order:
            return ResponseHandler(success=False, message=messages.ORDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        return ResponseHandler(message='success', data=self.serializer_class(order).data, status=status.HTTP_200_OK)
