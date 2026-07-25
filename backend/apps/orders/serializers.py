from rest_framework import serializers

from apps.games.models import Product
from apps.orders.models import Order, OrderItem, Payment


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class PaymentCreateRequestSerializer(serializers.Serializer):
    order = serializers.IntegerField()


class OrderSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
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

    def create(self, validated_data):
        order = super().create(validated_data)
        order.total_price = order.product.price
        order.save(update_fields=("total_price",))
        OrderItem.objects.create(
            order=order,
            product=order.product,
            product_title=order.product.title,
            quantity=1,
            unit_price=order.product.price,
        )
        return order


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


class CheckoutOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "status",
            "total_price",
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
    product = serializers.CharField(
        source="product.title",
        read_only=True,
    )

    class Meta:
        model = Order
        fields = [
            "order_number",
            "product",
            "status",
            "price_paid",
            "created_at",
            "paid_at",
        ]


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
