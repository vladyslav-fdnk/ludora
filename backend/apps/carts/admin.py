from django.contrib import admin

from apps.carts.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("product", "quantity", "created_at", "updated_at")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "updated_at")
    search_fields = ("user__email",)
    list_select_related = ("user",)
    readonly_fields = ("user", "created_at", "updated_at")
    inlines = (CartItemInline,)

