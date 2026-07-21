from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.services import pay_order
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer


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

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": "Payment successful",
                "order_id": order.id,
                "license_key": order.license_key.value,
            }
        )