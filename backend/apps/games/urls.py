from django.urls import path

from apps.games.views import ProductDetailAPIView, ProductListAPIView

app_name = "games"

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="product-list"),
    path("products/<int:pk>/", ProductDetailAPIView.as_view(), name="product-detail"),
]