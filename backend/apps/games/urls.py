from django.urls import path

from apps.games.views import (
    ProductCreateAPIView,
    ProductDeleteAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    ProductUpdateAPIView,
)

app_name = "games"


urlpatterns = [
    path(
        "products/",
        ProductListAPIView.as_view(),
        name="product-list",
    ),
    path(
        "products/<int:pk>/",
        ProductDetailAPIView.as_view(),
        name="product-detail",
    ),
    path(
        "products/create/",
        ProductCreateAPIView.as_view(),
        name="product-create",
    ),
    path(
        "products/<int:pk>/update/",
        ProductUpdateAPIView.as_view(),
        name="product-update",
    ),
    path(
        "products/<int:pk>/delete/",
        ProductDeleteAPIView.as_view(),
        name="product-delete",
    ),
]
