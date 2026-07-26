from django.urls import path

from apps.orders.payment_views import PaymentCreateAPIView
from apps.orders.views import (
    MyOrdersAPIView,
    OrderDetailAPIView,
    OrderListCreateAPIView,
    OrderPayAPIView,
)

app_name = "orders"

urlpatterns = [
    path(
        "",
        OrderListCreateAPIView.as_view(),
        name="order-list",
    ),
    path(
        "my/",
        MyOrdersAPIView.as_view(),
        name="my-orders",
    ),
    path(
        "<int:pk>/",
        OrderDetailAPIView.as_view(),
        name="order-detail",
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
