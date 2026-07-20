from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import SearchFilter

from apps.games.models import Product
from apps.games.serializers import (
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
)


class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.filter(
        is_active=True
    ).order_by("title")

    serializer_class = ProductListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
    ]

    filterset_fields = [
        "platform",
        "product_type",
        "categories",
    ]

    search_fields = [
        "title",
        "description",
    ]


class ProductDetailAPIView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductDetailSerializer


class ProductCreateAPIView(generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductWriteSerializer


class ProductUpdateAPIView(generics.UpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductWriteSerializer


class ProductDeleteAPIView(generics.DestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductDetailSerializer