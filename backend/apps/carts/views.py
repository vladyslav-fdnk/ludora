from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.exceptions import CartError
from apps.carts.models import CartItem
from apps.carts.serializers import (
    AddCartItemSerializer,
    CartItemSerializer,
    CartSerializer,
    CheckoutResponseSerializer,
    UpdateCartItemSerializer,
)
from apps.carts.services import (
    add_cart_item,
    checkout_cart,
    get_or_create_cart,
    set_cart_item_quantity,
)
from apps.orders.serializers import ErrorResponseSerializer


def cart_queryset(cart):
    return (
        type(cart)
        .objects.filter(pk=cart.pk)
        .prefetch_related("items__product__platform")
        .get()
    )


class CartAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: CartSerializer})
    def get(self, request):
        return Response(CartSerializer(cart_queryset(get_or_create_cart(request.user))).data)


class CartItemCreateAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=AddCartItemSerializer,
        responses={
            201: CartItemSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = add_cart_item(request.user, **serializer.validated_data)
        except CartError as error:
            return Response(
                {"error": str(error)},
                status=error.status_code,
            )
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CartItemDetailAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def _item(self, request, pk):
        return (
            CartItem.objects.filter(pk=pk, cart__user=request.user)
            .select_related("product", "product__platform")
            .first()
        )

    @extend_schema(request=UpdateCartItemSerializer, responses={200: CartItemSerializer})
    def patch(self, request, pk):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if self._item(request, pk) is None:
            return Response({"error": "Cart item not found."}, status=404)
        item = set_cart_item_quantity(request.user, pk, serializer.validated_data["quantity"])
        return Response(CartItemSerializer(item).data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        deleted, _ = CartItem.objects.filter(pk=pk, cart__user=request.user).delete()
        if not deleted:
            return Response({"error": "Cart item not found."}, status=404)
        return Response(status=204)


class CartClearAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={204: None})
    def delete(self, request):
        cart = get_or_create_cart(request.user)
        cart.items.all().delete()
        return Response(status=204)


class CartCheckoutAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=None,
        responses={
            201: CheckoutResponseSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer),
            409: OpenApiResponse(response=ErrorResponseSerializer),
        },
    )
    def post(self, request):
        try:
            order = checkout_cart(request.user)
        except CartError as error:
            return Response({"error": str(error)}, status=error.status_code)
        order = order.__class__.objects.prefetch_related("items").get(pk=order.pk)
        return Response(
            CheckoutResponseSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )

