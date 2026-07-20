from rest_framework import serializers

from apps.games.models import Category, Platform, Product


class PlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = ["id", "name", "slug"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class ProductListSerializer(serializers.ModelSerializer):
    platform = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "slug",
            "price",
            "platform",
            "product_type",
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    platform = serializers.StringRelatedField()
    categories = serializers.StringRelatedField(many=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "slug",
            "price",
            "platform",
            "product_type",
            "description",
            "categories",
            "is_active",
        ]