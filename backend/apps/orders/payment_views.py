from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order
from apps.orders.payment_services import create_payment
from apps.orders.serializers import (
    ErrorResponseSerializer,
    PaymentCreateRequestSerializer,
    PaymentSerializer,
)


class PaymentCreateAPIView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        request=PaymentCreateRequestSerializer,
        responses={
            201: PaymentSerializer,
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="A payment cannot be created for the order.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="The order was not found for the authenticated user.",
            ),
        },
        description="Create a payment for an owned order.",
    )
    def post(self, request):
        order_id = request.data.get("order")

        try:
            order = Order.objects.get(
                id=order_id,
                user=request.user,
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payment = create_payment(order)
        except OrderPaymentError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PaymentSerializer(payment)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )
