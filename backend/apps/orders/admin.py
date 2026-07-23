from django.contrib import admin

from apps.orders.models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "product",
        "email",
        "status",
        "created_at",
    ]

    list_filter = [
        "status",
    ]
