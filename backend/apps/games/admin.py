from django.contrib import admin
from django.db.models import Count, Q

from apps.games.models import Category, LicenseKey, Platform, Product


def mask_license_key(value):
    """Mask a license key while retaining enough context to identify it."""
    value = value or ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * (len(value) - 8)}{value[-4:]}"


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


class LicenseKeyInline(admin.TabularInline):
    model = LicenseKey
    fields = ("masked_key", "status", "created_at", "sold_at", "assigned_order")
    readonly_fields = fields
    extra = 0
    show_change_link = True
    verbose_name_plural = "License keys"

    @admin.display(description="Key")
    def masked_key(self, obj):
        return mask_license_key(obj.value)

    @admin.display(description="Assigned order", ordering="order__order_number")
    def assigned_order(self, obj):
        return getattr(obj, "order", None)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "platform",
        "product_type",
        "price",
        "available_keys_count",
        "sold_keys_count",
        "total_keys_count",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active", "product_type", "platform", "categories")
    search_fields = (
        "title",
        "slug",
        "description",
        "platform__name",
        "categories__name",
    )
    autocomplete_fields = ("platform",)
    filter_horizontal = ("categories",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    list_select_related = ("platform",)
    ordering = ("title",)
    fieldsets = (
        (None, {"fields": ("title", "slug", "description")}),
        (
            "Catalogue",
            {
                "fields": (
                    "product_type",
                    "platform",
                    "categories",
                    "price",
                    "is_active",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    actions = ("activate_products", "deactivate_products")
    inlines = (LicenseKeyInline,)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _available_keys_count=Count(
                    "license_keys",
                    filter=Q(license_keys__status=LicenseKey.Status.AVAILABLE),
                    distinct=True,
                ),
                _sold_keys_count=Count(
                    "license_keys",
                    filter=Q(license_keys__status=LicenseKey.Status.SOLD),
                    distinct=True,
                ),
                _total_keys_count=Count("license_keys", distinct=True),
            )
        )

    @admin.display(description="Available keys", ordering="_available_keys_count")
    def available_keys_count(self, obj):
        return obj._available_keys_count

    @admin.display(description="Sold keys", ordering="_sold_keys_count")
    def sold_keys_count(self, obj):
        return obj._sold_keys_count

    @admin.display(description="Total keys", ordering="_total_keys_count")
    def total_keys_count(self, obj):
        return obj._total_keys_count

    @admin.action(description="Activate selected products")
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} product(s) activated.")

    @admin.action(description="Deactivate selected products")
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} product(s) deactivated.")


@admin.register(LicenseKey)
class LicenseKeyAdmin(admin.ModelAdmin):
    list_display = ("product", "masked_key", "is_sold", "assigned_order")
    list_filter = ("status", "product", "product__platform")
    search_fields = ("value", "product__title", "order__order_number")
    autocomplete_fields = ("product",)
    readonly_fields = ("status", "sold_at", "created_at", "assigned_order")
    list_select_related = ("product", "product__platform", "order")
    ordering = ("product__title", "id")

    @admin.display(description="Key")
    def masked_key(self, obj):
        return mask_license_key(obj.value)

    @admin.display(boolean=True, description="Sold", ordering="status")
    def is_sold(self, obj):
        return obj.status == LicenseKey.Status.SOLD

    @admin.display(description="Assigned order", ordering="order__order_number")
    def assigned_order(self, obj):
        return getattr(obj, "order", None)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == LicenseKey.Status.SOLD:
            fields.extend(field.name for field in obj._meta.fields if field.editable)
            return tuple(dict.fromkeys(fields))
        if obj and (
            obj.status != LicenseKey.Status.AVAILABLE
            or self.assigned_order(obj) is not None
        ):
            fields.extend(("product", "value"))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status == LicenseKey.Status.SOLD:
            return False
        return super().has_delete_permission(request, obj)
