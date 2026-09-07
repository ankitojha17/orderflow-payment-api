import django_filters
from services.models import Order, Product


class OrderFilterSet(django_filters.FilterSet):
    class Meta:
        model = Order
        fields = ['status']


class ProductFilterSet(django_filters.FilterSet):
    search = django_filters.CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = Product
        fields = ['search']
