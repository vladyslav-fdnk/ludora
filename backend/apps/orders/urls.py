from django.urls import path

from apps.orders.views import (
    OrderCreateAPIView,
    OrderPayAPIView,
)

app_name = "orders"

urlpatterns = [
    path(
        "",
        OrderCreateAPIView.as_view(),
        name="order-create",
    ),

    path(
        "<int:pk>/pay/",
        OrderPayAPIView.as_view(),
        name="order-pay",
    ),
]