from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.services import pay_order
from apps.orders.models import Order
from apps.orders.serializers import (
    OrderSerializer,
    OrderPaymentSerializer,
)
from apps.orders.exceptions import OrderPaymentError


class OrderCreateAPIView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class OrderPayAPIView(APIView):

    def post(self, request, pk):
        try:
            order = pay_order(pk)

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        except OrderPaymentError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderPaymentSerializer(order)

        return Response(
            serializer.data
        )