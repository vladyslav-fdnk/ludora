from rest_framework import generics

from apps.games.models import Product
from apps.games.serializers import (
    ProductDetailSerializer,
    ProductListSerializer,
)


class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.filter(is_active=True).order_by("title")
    serializer_class = ProductListSerializer


class ProductDetailAPIView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductDetailSerializer