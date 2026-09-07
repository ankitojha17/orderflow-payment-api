from rest_framework import serializers

from services.models import Product
from services.constants import messages


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class CreateOrderSerializer(serializers.Serializer):
    """
    Validation only — no database writes happen here.
    Order creation itself (stock locking, price snapshotting, totals) is
    business logic and lives in CreateOrderView, not here.

    Negative cases are checked first in every validate_* method below,
    so the earliest possible failure short-circuits the rest of the check.
    """
    items = OrderItemInputSerializer(many=True)

    def validate_items(self, items):
        # Negative case first: empty cart.
        if not items:
            raise serializers.ValidationError("At least one item is required.")

        product_ids = [item['product_id'] for item in items]

        # Negative case: same product listed twice in one request.
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError(messages.DUPLICATE_PRODUCT_IN_ORDER)

        products_by_id = {
            product.id: product
            for product in Product.objects.filter(id__in=product_ids, is_deleted=False, is_active=True)
        }

        for item in items:
            product = products_by_id.get(item['product_id'])

            # Negative case: product doesn't exist / inactive / deleted.
            if not product:
                raise serializers.ValidationError(messages.PRODUCT_NOT_FOUND)

            # Negative case: not enough stock — this is a friendly pre-check
            # for a fast validation error. It is NOT the authoritative check;
            # the view re-checks with select_for_update() inside a transaction
            # to guard against a race condition between this check and the write.
            if product.stock_quantity < item['quantity']:
                raise serializers.ValidationError(f"Insufficient stock for {product.name}.")

        return items
