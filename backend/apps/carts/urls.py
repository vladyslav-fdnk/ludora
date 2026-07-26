from django.urls import path

from apps.carts.views import (
    CartAPIView,
    CartCheckoutAPIView,
    CartClearAPIView,
    CartItemCreateAPIView,
    CartItemDetailAPIView,
)

app_name = "carts"

urlpatterns = [
    path("", CartAPIView.as_view(), name="detail"),
    path("items/", CartItemCreateAPIView.as_view(), name="item-create"),
    path("items/<int:pk>/", CartItemDetailAPIView.as_view(), name="item-detail"),
    path("clear/", CartClearAPIView.as_view(), name="clear"),
    path("checkout/", CartCheckoutAPIView.as_view(), name="checkout"),
]

