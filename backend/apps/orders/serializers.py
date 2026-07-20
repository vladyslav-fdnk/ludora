from rest_framework import serializers

from apps.orders.models import Order
from apps.games.models import Product


class OrderSerializer(serializers.ModelSerializer):

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all()
    )

    class Meta:
        model = Order

        fields = [
            "id",
            "product",
            "email",
            "status",
            "license_key",
            "created_at",
        ]

        read_only_fields = [
            "status",
            "license_key",
            "created_at",
        ]