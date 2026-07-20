from django.contrib import admin

from apps.games.models import Category, LicenseKey, Platform, Product


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "product_type", "price", "is_active")
    list_filter = ("platform", "product_type", "is_active")
    search_fields = ("title", "description")
    autocomplete_fields = ("platform",)
    filter_horizontal = ("categories",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(LicenseKey)
class LicenseKeyAdmin(admin.ModelAdmin):
    list_display = ("product", "status", "created_at", "sold_at")
    list_filter = ("status",)
    search_fields = ("value",)
    autocomplete_fields = ("product",)
