from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.models import Order
from apps.orders.serializers import PaymentSerializer
from apps.orders.payment_services import create_payment


class PaymentCreateAPIView(APIView):

    def post(self, request):
        order_id = request.data.get("order")

        try:
            order = Order.objects.get(id=order_id)

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        payment = create_payment(order)

        serializer = PaymentSerializer(payment)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )