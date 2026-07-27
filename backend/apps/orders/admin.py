from django.contrib import admin
from django.utils.html import format_html

from apps.orders.models import Order, OrderItem, Payment


def status_badge(label, color):
    """Render a compact status label compatible with the standard admin."""
    return format_html(
        '<span style="display:inline-block;padding:2px 7px;border-radius:10px;'
        'background:{};color:white;font-weight:600">{}</span>',
        color,
        label,
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "product_title",
        "quantity",
        "unit_price",
    )
    show_change_link = True
    verbose_name_plural = "Order items"

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    fields = (
        "payment_id",
        "status",
        "provider",
        "transaction_id",
        "amount",
        "created_at",
        "paid_at",
    )
    readonly_fields = fields
    extra = 0
    show_change_link = True
    verbose_name_plural = "Payments"

    @admin.display(description="Payment ID", ordering="id")
    def payment_id(self, obj):
        return obj.pk

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "product",
        "source",
        "total_price",
        "status_badge",
        "price_paid",
        "created_at",
        "paid_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "source",
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
        "source",
        "total_price",
        "status",
        "price_paid",
        "license_key",
        "created_at",
        "updated_at",
        "paid_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = (OrderItemInline, PaymentInline)

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Order.Status.CREATED: "#6b7280",
            Order.Status.PAID: "#15803d",
            Order.Status.CANCELLED: "#b91c1c",
        }
        return status_badge(obj.get_status_display(), colors[obj.status])

    @admin.display(description="Customer", ordering="user__email")
    def customer(self, obj):
        return obj.user.email if obj.user else obj.email

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "provider",
        "transaction_id",
        "status_badge",
        "amount",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "provider", "created_at")
    search_fields = (
        "order__order_number",
        "order__email",
        "order__user__email",
        "transaction_id",
        "provider",
    )
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

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Payment.Status.CREATED: "#6b7280",
            Payment.Status.PENDING: "#b45309",
            Payment.Status.PAID: "#15803d",
            Payment.Status.FAILED: "#b91c1c",
        }
        return status_badge(obj.get_status_display(), colors[obj.status])

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
