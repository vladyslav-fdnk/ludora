from rest_framework import serializers

from apps.games.models import Product
from apps.orders.models import Order, OrderItem, Payment
from apps.orders.services import create_direct_order


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class PaymentCreateRequestSerializer(serializers.Serializer):
    order = serializers.IntegerField()


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderItem
        fields = (
            "product",
            "product_title",
            "quantity",
            "unit_price",
            "line_total",
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "product",
            "email",
            "status",
            "source",
            "total_price",
            "items",
            "license_key",
            "created_at",
        )
        read_only_fields = (
            "status",
            "source",
            "total_price",
            "license_key",
            "created_at",
        )

    def create(self, validated_data):
        return create_direct_order(**validated_data)


class CheckoutOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "source",
            "total_price",
            "price_paid",
            "items",
            "created_at",
        )


class OrderPaymentSerializer(serializers.ModelSerializer):
    license_key = serializers.CharField(source="license_key.value", read_only=True)

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

    def get_message(self, obj) -> str:
        if obj.status == Order.Status.PAID:
            return "Payment successful"

        return "Payment pending"


class MyOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    product = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "product",
            "status",
            "source",
            "total_price",
            "price_paid",
            "created_at",
            "paid_at",
            "items",
        )

    def get_product(self, obj) -> str | None:
        first_item = next(iter(obj.items.all()), None)
        return first_item.product_title if first_item else None


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "status",
            "amount",
            "created_at",
        ]

        read_only_fields = [
            "status",
            "amount",
            "created_at",
        ]
