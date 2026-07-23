from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order
from apps.orders.serializers import (
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
        return (
            Order.objects.filter(
                user=self.request.user,
            )
            .select_related("product")
            .order_by("-created_at")
        )
