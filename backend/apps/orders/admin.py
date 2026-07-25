from django.contrib import admin

from apps.orders.models import Order, Payment


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "product",
        "status",
        "price_paid",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "created_at",
        "product",
        "product__platform",
    )
    search_fields = (
        "order_number",
        "email",
        "user__email",
        "product__title",
    )
    list_select_related = ("user", "product", "product__platform", "license_key")
    readonly_fields = (
        "order_number",
        "user",
        "email",
        "product",
        "status",
        "price_paid",
        "license_key",
        "created_at",
        "updated_at",
        "paid_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Customer", ordering="user__email")
    def customer(self, obj):
        return obj.user.email if obj.user else obj.email

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "status", "amount", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "order__email", "order__user__email")
    list_select_related = ("order", "order__user")
    readonly_fields = (
        "order",
        "status",
        "provider",
        "transaction_id",
        "amount",
        "created_at",
        "paid_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
