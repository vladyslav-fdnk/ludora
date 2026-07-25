from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.games.models import Product
from apps.games.serializers import (
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
)
from apps.permissions import IsStaffUser


class ProductListAPIView(generics.ListAPIView):
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("platform")
        .prefetch_related("categories")
    )

    serializer_class = ProductListSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    ordering_fields = [
        "price",
        "title",
        "created_at",
    ]

    ordering = ["title"]

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
    permission_classes = [IsStaffUser]


class ProductUpdateAPIView(generics.UpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductWriteSerializer
    permission_classes = [IsStaffUser]


class ProductDeleteAPIView(generics.UpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductDetailSerializer
    permission_classes = [IsStaffUser]

    def delete(self, request, *args, **kwargs):
        product = self.get_object()

        product.is_active = False
        product.save(update_fields=["is_active"])

        return Response(status=204)
