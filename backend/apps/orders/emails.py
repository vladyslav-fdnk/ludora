from django.conf import settings
from django.core.mail import EmailMessage

from apps.orders.models import Order


def assigned_license_key_values(order: Order) -> list[str]:
    """Return the fulfilled keys in stable order for an order email."""
    values = [
        assignment.license_key.value
        for item in order.items.all()
        for assignment in item.license_assignments.all()
    ]
    if values:
        return values
    if order.license_key_id is not None:
        return [order.license_key.value]
    return []


def has_complete_fulfilment(order: Order) -> bool:
    """Check that every purchased unit has a sold license key."""
    items = list(order.items.all())
    assignments = [
        assignment
        for item in items
        for assignment in item.license_assignments.all()
    ]
    if assignments:
        return (
            len(assignments) == sum(item.quantity for item in items)
            and all(
                assignment.license_key.status == assignment.license_key.Status.SOLD
                for assignment in assignments
            )
        )
    return (
        order.source == Order.Source.DIRECT
        and order.license_key_id is not None
        and order.license_key.status == order.license_key.Status.SOLD
    )


def build_order_confirmation_email(order: Order) -> EmailMessage:
    """Build the plain-text confirmation from committed order state."""
    product_lines = [
        f"- {item.product_title} × {item.quantity}"
        for item in order.items.all()
    ]
    if not product_lines and order.product_id is not None:
        product_lines = [f"- {order.product.title}"]
    license_key_lines = [
        f"- {value}" for value in assigned_license_key_values(order)
    ]

    body = "\n".join(
        [
            "Thank you for your purchase.",
            "",
            f"Order: {order.order_number}",
            "",
            "Products:",
            *product_lines,
            "",
            "License keys:",
            *license_key_lines,
            "",
            f"Total paid: {order.price_paid}",
            "",
            "If you need help with your order, please contact Ludora support.",
        ]
    )

    return EmailMessage(
        subject=f"Ludora order confirmation — {order.order_number}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
