from django.urls import path

from apps.orders.views import (
    OrderCreateAPIView,
    OrderPayAPIView,
)


urlpatterns = [

    path(
        "",
        OrderCreateAPIView.as_view()
    ),

    path(
        "<int:pk>/pay/",
        OrderPayAPIView.as_view()
    ),

]