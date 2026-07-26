from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order
from apps.orders.serializers import (
    ErrorResponseSerializer,
    MyOrderSerializer,
    OrderPaymentSerializer,
    OrderSerializer,
)
from apps.orders.services import pay_order


class OrderCreateAPIView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [
        IsAuthenticated,
    ]

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            email=self.request.user.email,
        )


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


class MyOrdersAPIView(generics.ListAPIView):
    serializer_class = MyOrderSerializer
    permission_classes = [
        IsAuthenticated,
    ]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()

        return (
            Order.objects.filter(
                user=self.request.user,
            )
            .prefetch_related("items")
            .order_by("-created_at")
        )
