from decimal import Decimal

from rest_framework import serializers

from apps.carts.models import MAX_CART_ITEM_QUANTITY, Cart, CartItem
from apps.games.serializers import ProductListSerializer
from apps.orders.serializers import CheckoutOrderSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    unit_price = serializers.DecimalField(
        source="product.price", max_digits=10, decimal_places=2, read_only=True
    )
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ("id", "product", "quantity", "unit_price", "line_total")

    def get_line_total(self, obj) -> Decimal:
        return obj.line_total


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_quantity = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ("id", "items", "total_quantity", "total_price")

    def get_total_quantity(self, obj) -> int:
        return sum(item.quantity for item in obj.items.all())

    def get_total_price(self, obj) -> Decimal:
        return sum((item.line_total for item in obj.items.all()), start=Decimal("0.00"))


class AddCartItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_CART_ITEM_QUANTITY,
    )


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_CART_ITEM_QUANTITY,
    )


class CheckoutResponseSerializer(CheckoutOrderSerializer):
    pass

