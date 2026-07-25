from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.carts.exceptions import (
    CartConflictError,
    EmptyCartError,
    ProductUnavailableError,
)
from apps.carts.models import MAX_CART_ITEM_QUANTITY, Cart, CartItem
from apps.games.models import Product
from apps.orders.models import Order, OrderItem


def get_or_create_cart(user) -> Cart:
    try:
        return Cart.objects.get(user=user)
    except Cart.DoesNotExist:
        try:
            with transaction.atomic():
                return Cart.objects.create(user=user)
        except IntegrityError:
            return Cart.objects.get(user=user)


@transaction.atomic
def add_cart_item(user, product: int, quantity: int) -> CartItem:
    cart = get_or_create_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    try:
        product_object = Product.objects.get(pk=product, is_active=True)
    except Product.DoesNotExist as exc:
        raise ProductUnavailableError("Product is unavailable.") from exc

    item = (
        CartItem.objects.select_for_update()
        .filter(cart=cart, product=product_object)
        .first()
    )
    new_quantity = quantity + (item.quantity if item else 0)
    if new_quantity > MAX_CART_ITEM_QUANTITY:
        raise CartConflictError(
            f"Cart item quantity cannot exceed {MAX_CART_ITEM_QUANTITY}."
        )
    if item:
        item.quantity = new_quantity
        item.save(update_fields=("quantity", "updated_at"))
        return item
    return CartItem.objects.create(
        cart=cart, product=product_object, quantity=quantity
    )


@transaction.atomic
def set_cart_item_quantity(user, item_id: int, quantity: int) -> CartItem:
    item = (
        CartItem.objects.select_for_update()
        .select_related("product")
        .get(pk=item_id, cart__user=user)
    )
    item.quantity = quantity
    item.full_clean()
    item.save(update_fields=("quantity", "updated_at"))
    return item


@transaction.atomic
def checkout_cart(user) -> Order:
    cart = get_or_create_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    items = list(
        CartItem.objects.select_for_update()
        .filter(cart=cart)
        .select_related("product")
        .order_by("id")
    )
    if not items:
        raise EmptyCartError("The cart is empty.")
    unavailable = [item.product.title for item in items if not item.product.is_active]
    if unavailable:
        raise ProductUnavailableError("A cart product is no longer available.")

    total = sum(
        (item.product.price * item.quantity for item in items),
        start=Decimal("0.00"),
    )
    order = Order.objects.create(
        user=user,
        email=user.email,
        total_price=total,
        source=Order.Source.CART,
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=item.product,
                product_title=item.product.title,
                quantity=item.quantity,
                unit_price=item.product.price,
            )
            for item in items
        ]
    )
    CartItem.objects.filter(cart=cart).delete()
    return order
