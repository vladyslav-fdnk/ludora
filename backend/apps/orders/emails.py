from django.conf import settings
from django.core.mail import EmailMessage

from apps.orders.models import Order


def build_order_confirmation_email(order: Order) -> EmailMessage:
    """Build the plain-text confirmation from committed order state."""
    product_lines = [
        f"- {item.product_title} × {item.quantity}"
        for item in order.items.all()
    ]
    if not product_lines and order.product_id is not None:
        product_lines = [f"- {order.product.title}"]

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
            f"- {order.license_key.value}",
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
