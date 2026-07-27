from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order
from apps.orders.selectors import user_order_details, user_order_history
from apps.orders.serializers import (
    ErrorResponseSerializer,
    MyOrderDetailSerializer,
    MyOrderListSerializer,
    OrderHistorySerializer,
    OrderPaymentSerializer,
    OrderSerializer,
)
from apps.orders.services import pay_order


class OrderVisibilityMixin:
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()

        queryset = Order.objects.prefetch_related("items").order_by(
            "-created_at",
            "-id",
        )
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)


class OrderListCreateAPIView(OrderVisibilityMixin, generics.ListCreateAPIView):
    queryset = Order.objects.all()
    permission_classes = [
        IsAuthenticated,
    ]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return OrderHistorySerializer
        return OrderSerializer

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            email=self.request.user.email,
        )

    @extend_schema(
        responses={
            200: OrderHistorySerializer(many=True),
            401: OpenApiResponse(description="JWT authentication is required."),
        },
        description=(
            "List orders visible to the authenticated user, newest first. "
            "Regular users see only their own orders; staff users see all orders."
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class OrderPayAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        request=None,
        responses={
            200: OrderPaymentSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="The order cannot be paid.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="The order was not found for the authenticated user.",
            ),
        },
        description="Pay an owned order and return its payment result.",
    )
    def post(self, request, pk):

        try:
            order = Order.objects.get(
                id=pk,
                user=request.user,
            )

        except Order.DoesNotExist:
            return Response(
                {
                    "error": "Order not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            order = pay_order(order.id)

        except OrderPaymentError as error:
            return Response(
                {
                    "error": str(error),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderPaymentSerializer(
            order,
        )

        return Response(
            serializer.data,
        )


class OrderDetailAPIView(OrderVisibilityMixin, generics.RetrieveAPIView):
    serializer_class = OrderHistorySerializer
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        responses={
            200: OrderHistorySerializer,
            401: OpenApiResponse(description="JWT authentication is required."),
            404: OpenApiResponse(
                description="The order does not exist or is not visible to this user."
            ),
        },
        description=(
            "Retrieve one visible order. Orders outside a regular user's ownership "
            "scope are returned as not found; staff users may retrieve any order."
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MyOrdersAPIView(generics.ListAPIView):
    serializer_class = MyOrderListSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return user_order_history(user=self.request.user)


class MyOrderDetailAPIView(generics.RetrieveAPIView):
    serializer_class = MyOrderDetailSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return user_order_details(user=self.request.user)
