from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.models import LicenseKey
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer


class OrderCreateAPIView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class OrderPayAPIView(APIView):

    @transaction.atomic
    def post(self, request, pk):

        try:
            order = Order.objects.select_for_update().get(
                id=pk
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status == Order.Status.PAID:
            return Response(
                {"error": "Already paid"},
                status=status.HTTP_400_BAD_REQUEST
            )

        license_key = LicenseKey.objects.select_for_update().filter(
            product=order.product,
            status=LicenseKey.Status.AVAILABLE,
        ).first()

        if not license_key:
            return Response(
                {"error": "No keys available"},
                status=status.HTTP_400_BAD_REQUEST
            )

        license_key.status = LicenseKey.Status.SOLD
        license_key.save()

        order.license_key = license_key
        order.status = Order.Status.PAID
        order.save()

        return Response(
            {
                "message": "Payment successful",
                "order_id": order.id,
                "license_key": license_key.value,
            }
        )