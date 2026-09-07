from rest_framework import generics, status
from django_filters.rest_framework import DjangoFilterBackend

from services.models import Product
from services.serializer import ProductSerializer
from services.utils.filters import ProductFilterSet
from services.utils.pagination import StandardResultsPagination
from services.utils.response_handler import ResponseHandler


class ProductListView(generics.ListAPIView):
    """Public endpoint. Supports ?search=<name> and standard pagination."""
    serializer_class = ProductSerializer
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ProductFilterSet

    def get_queryset(self):
        return Product.objects.filter(is_deleted=False, is_active=True)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.serializer_class(page, many=True)
        return ResponseHandler(
            message='success', data=serializer.data, meta=self.paginator.get_meta(), status=status.HTTP_200_OK
        )
