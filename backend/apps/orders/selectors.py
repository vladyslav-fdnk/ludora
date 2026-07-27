from django.db.models import IntegerField, Prefetch, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.orders.models import LicenseAssignment, Order, OrderItem, Payment


def user_order_history(*, user) -> QuerySet[Order]:
    """Return a user's orders prepared for the order-history list."""
    return (
        Order.objects.filter(user=user)
        .annotate(
            number_of_items=Coalesce(
                Sum("items__quantity"),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("-created_at", "-id")
    )


def user_order_details(*, user) -> QuerySet[Order]:
    """Return a user's orders with all detail representation data loaded."""
    assignments = LicenseAssignment.objects.select_related("license_key").order_by(
        "id"
    )
    items = OrderItem.objects.select_related("product").prefetch_related(
        Prefetch("license_assignments", queryset=assignments)
    )
    payments = Payment.objects.order_by("created_at", "id")
    return (
        Order.objects.filter(user=user)
        .select_related("product", "license_key")
        .prefetch_related(
            Prefetch("items", queryset=items),
            Prefetch("payments", queryset=payments),
        )
    )
