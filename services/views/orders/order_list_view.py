from rest_framework import generics, status
from django_filters.rest_framework import DjangoFilterBackend

from services.models import Order
from services.serializer import OrderSerializer
from services.utils.authentication import Authentication
from services.utils.filters import OrderFilterSet
from services.utils.pagination import StandardResultsPagination
from services.utils.response_handler import ResponseHandler


class OrderListView(Authentication, generics.ListAPIView):
    """
    Requires a valid JWT. Supports ?status=paid and standard pagination.
    Staff users (is_staff=True) see every order; everyone else sees only
    their own — same endpoint, scoped by role rather than a separate admin API.
    """
    serializer_class = OrderSerializer
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilterSet

    def get_queryset(self):
        queryset = (
            Order.objects.select_related('user')
            .prefetch_related('items__product')
            .filter(is_deleted=False)
        )
        if not self.request.auth_user.is_staff:
            queryset = queryset.filter(user=self.request.auth_user)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.serializer_class(page, many=True)
        return ResponseHandler(
            message='success', data=serializer.data, meta=self.paginator.get_meta(), status=status.HTTP_200_OK
        )
