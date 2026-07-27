from html import escape

from app.api.schemas import OrderDetail, OrderSummary
from app.localization import Translator


def format_order_history(
    orders: tuple[OrderSummary, ...], language: str, translator: Translator
) -> str:
    if not orders:
        return translator.get("orders.empty", language)
    lines = [translator.get("orders.title", language)]
    for order in orders:
        lines.extend(
            [
                "",
                translator.get("orders.id", language, value=order.id),
                translator.get(
                    "orders.status", language, value=escape(order.status)
                ),
                translator.get(
                    "orders.created",
                    language,
                    value=order.created_at.date().isoformat(),
                ),
                translator.get(
                    "orders.items", language, value=order.number_of_items
                ),
                translator.get(
                    "orders.total",
                    language,
                    value=format(order.total_price, ".2f"),
                ),
            ]
        )
    return "\n".join(lines)


def format_order_detail(
    order: OrderDetail, language: str, translator: Translator
) -> str:
    lines = [
        translator.get("order_detail.title", language, order_id=order.id),
        translator.get(
            "orders.status", language, value=escape(order.status)
        ),
        translator.get(
            "orders.created",
            language,
            value=order.created_at.date().isoformat(),
        ),
        "",
        translator.get("order_detail.products", language),
    ]
    lines.extend(
        translator.get(
            "order_detail.item",
            language,
            title=escape(item.product_title),
            quantity=item.quantity,
            unit_price=format(item.unit_price, ".2f"),
            line_total=format(item.line_total, ".2f"),
        )
        for item in order.items
    )
    lines.extend(["", translator.get("order_detail.payments", language)])
    if order.payments:
        lines.extend(
            translator.get(
                "order_detail.payment",
                language,
                status=escape(payment.status),
                provider=escape(payment.provider or "—"),
                transaction_id=escape(payment.transaction_id or "—"),
                amount=format(payment.amount, ".2f"),
            )
            for payment in order.payments
        )
    else:
        lines.append(translator.get("order_detail.no_payments", language))

    license_keys = tuple(
        assignment.license_key
        for item in order.items
        for assignment in item.license_assignments
        if assignment.license_key
    )
    if license_keys:
        lines.extend(
            [
                "",
                translator.get("order_detail.license_keys", language),
                *(f"<code>{escape(key)}</code>" for key in license_keys),
            ]
        )
    return "\n".join(lines)
