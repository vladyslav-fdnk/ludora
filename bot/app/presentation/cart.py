from html import escape

from app.api.schemas import Cart, CheckoutOrder
from app.localization import Translator


def format_cart(cart: Cart, language: str, translator: Translator) -> str:
    if not cart.items:
        return translator.get("cart.empty", language)
    lines = [translator.get("cart.title", language), ""]
    for item in cart.items:
        lines.append(
            translator.get(
                "cart.item",
                language,
                title=escape(item.product.title),
                quantity=item.quantity,
                unit_price=format(item.unit_price, ".2f"),
                line_total=format(item.line_total, ".2f"),
            )
        )
    lines.extend(
        [
            "",
            translator.get("cart.quantity", language, quantity=cart.total_quantity),
            translator.get(
                "cart.total", language, total=format(cart.total_price, ".2f")
            ),
        ]
    )
    return "\n".join(lines)


def format_order(
    order: CheckoutOrder, language: str, translator: Translator
) -> str:
    lines = [
        translator.get(
            "checkout.success",
            language,
            order_number=escape(order.order_number),
        ),
        "",
    ]
    lines.extend(
        translator.get(
            "checkout.item",
            language,
            title=escape(item.product_title),
            quantity=item.quantity,
            line_total=format(item.line_total, ".2f"),
        )
        for item in order.items
    )
    lines.extend(
        [
            "",
            translator.get(
                "checkout.total", language, total=format(order.total_price, ".2f")
            ),
        ]
    )
    return "\n".join(lines)
