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

class OrderPaymentSerializer(serializers.ModelSerializer):
    license_key = serializers.CharField(
        source="license_key.value", 
        read_only=True
    )

    message = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "message",
            "order_number",
            "license_key",
            "price_paid",
            "paid_at",
        )
        
    def get_message(self, obj):
        if obj.status == Order.Status.PAID:
            return "Payment successful"

        return "Payment pending"