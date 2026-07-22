from django.urls import path

from apps.orders.views import (
    MyOrdersAPIView,
    OrderCreateAPIView,
    OrderPayAPIView,
)

from apps.orders.payment_views import PaymentCreateAPIView


app_name = "orders"

urlpatterns = [
    path(
        "",
        OrderCreateAPIView.as_view(),
        name="order-create",
    ),

    path(
        "my/",
        MyOrdersAPIView.as_view(),
        name="my-orders",
    ),

    path(
        "<int:pk>/pay/",
        OrderPayAPIView.as_view(),
        name="order-pay",
    ),

    path(
        "payments/",
        PaymentCreateAPIView.as_view(),
        name="payment-create",
    ),
]