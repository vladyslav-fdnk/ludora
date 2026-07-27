from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.carts.exceptions import CartItemNotFoundError, EmptyCartError
from apps.carts.models import Cart, CartItem
from apps.carts.services import add_cart_item, checkout_cart, set_cart_item_quantity
from apps.games.models import LicenseKey, Platform, Product
from apps.orders.models import Order, OrderItem, Payment

User = get_user_model()


class CartAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="x")
        self.other_user = User.objects.create_user(email="other@example.com", password="x")
        self.platform = Platform.objects.create(name="Steam", slug="steam")
        self.product = Product.objects.create(
            title="Portal <Two>",
            slug="portal-two",
            price=Decimal("12.50"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            is_active=True,
        )
        self.second = Product.objects.create(
            title="Half-Life",
            slug="half-life",
            price=Decimal("7.25"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
            is_active=True,
        )
        self.client.force_authenticate(self.user)

    def add(self, product=None, quantity=1):
        return self.client.post(
            "/api/cart/items/",
            {"product": (product or self.product).pk, "quantity": quantity},
            format="json",
        )

    def test_get_creates_one_empty_cart_automatically(self):
        first = self.client.get("/api/cart/")
        second = self.client.get("/api/cart/")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["items"], [])
        self.assertEqual(first.data["total_quantity"], 0)
        self.assertEqual(first.data["total_price"], Decimal("0.00"))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)

    def test_cart_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        for method, path, data in (
            ("get", "/api/cart/", None),
            ("post", "/api/cart/items/", {"product": self.product.pk, "quantity": 1}),
            ("delete", "/api/cart/clear/", None),
            ("post", "/api/cart/checkout/", None),
        ):
            response = getattr(self.client, method)(path, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_active_product_and_calculate_decimal_totals(self):
        response = self.add(quantity=2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cart = self.client.get("/api/cart/")
        item = cart.data["items"][0]
        self.assertEqual(item["product"]["id"], self.product.pk)
        self.assertEqual(item["quantity"], 2)
        self.assertTrue(item["is_active"])
        self.assertEqual(item["unit_price"], "12.50")
        self.assertEqual(item["line_total"], Decimal("25.00"))
        self.assertEqual(cart.data["total_quantity"], 2)
        self.assertEqual(cart.data["total_price"], Decimal("25.00"))

    def test_add_defaults_quantity_to_one(self):
        response = self.client.post(
            "/api/cart/items/",
            {"product": self.product.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["quantity"], 1)
        self.assertEqual(CartItem.objects.get().quantity, 1)

    def test_cart_marks_deactivated_product_as_inactive(self):
        self.add()
        self.product.is_active = False
        self.product.save(update_fields=("is_active",))

        response = self.client.get("/api/cart/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["items"][0]["is_active"])

    def test_rejects_inactive_missing_and_invalid_quantities(self):
        self.product.is_active = False
        self.product.save(update_fields=("is_active",))
        self.assertEqual(self.add().status_code, status.HTTP_400_BAD_REQUEST)
        for quantity in (0, -1, 100, "one"):
            self.product.is_active = True
            self.product.save(update_fields=("is_active",))
            self.assertEqual(self.add(quantity=quantity).status_code, 400)
        self.assertFalse(CartItem.objects.exists())

    def test_adding_same_product_increases_quantity_without_duplicate(self):
        self.add(quantity=2)
        response = self.add(quantity=3)
        self.assertEqual(response.data["quantity"], 5)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_adding_over_maximum_returns_conflict_and_preserves_quantity(self):
        self.add(quantity=99)
        response = self.add(quantity=1)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(CartItem.objects.get().quantity, 99)

    def test_update_delete_and_clear_are_user_isolated(self):
        item = CartItem.objects.create(
            cart=Cart.objects.create(user=self.other_user),
            product=self.product,
            quantity=2,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/cart/items/{item.pk}/", {"quantity": 3}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.delete(f"/api/cart/items/{item.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        own_id = self.add(quantity=2).data["id"]
        updated = self.client.patch(
            f"/api/cart/items/{own_id}/", {"quantity": 4}, format="json"
        )
        self.assertEqual(updated.data["quantity"], 4)
        self.assertEqual(self.client.delete(f"/api/cart/items/{own_id}/").status_code, 204)
        self.add()
        self.assertEqual(self.client.delete("/api/cart/clear/").status_code, 204)
        self.assertFalse(Cart.objects.get(user=self.user).items.exists())
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantity, 2)

    @patch("apps.carts.views.set_cart_item_quantity")
    def test_stale_item_update_returns_stable_404(self, update_quantity):
        update_quantity.side_effect = CartItemNotFoundError("Cart item not found.")

        response = self.client.patch(
            "/api/cart/items/999/",
            {"quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"error": "Cart item not found."})

    def test_nonexistent_item_update_returns_404(self):
        response = self.client.patch(
            "/api/cart/items/999999/",
            {"quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {"error": "Cart item not found."})

    def test_invalid_update_quantity_remains_validation_error(self):
        response = self.client.patch(
            "/api/cart/items/999999/",
            {"quantity": 0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_cart_response_has_bounded_queries(self):
        self.add()
        self.add(self.second, 2)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 5)

    def test_schema_documents_all_cart_endpoints(self):
        schema = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(schema.status_code, 200)
        paths = schema.data["paths"]
        for path in (
            "/api/cart/",
            "/api/cart/items/",
            "/api/cart/items/{id}/",
            "/api/cart/clear/",
            "/api/cart/checkout/",
        ):
            self.assertIn(path, paths)


class CheckoutAPITests(CartAPITests):
    def test_empty_cart_is_rejected_without_order(self):
        response = self.client.post("/api/cart/checkout/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_checkout_creates_owned_multi_item_order_with_snapshots(self):
        self.add(quantity=2)
        self.add(self.second, 3)
        self.product.price = Decimal("15.00")
        self.product.save(update_fields=("price",))
        response = self.client.post("/api/cart/checkout/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.email, self.user.email)
        self.assertEqual(order.source, Order.Source.CART)
        self.assertIsNone(order.product)
        self.assertEqual(order.total_price, Decimal("51.75"))
        self.assertEqual(order.items.count(), 2)
        first = order.items.get(product=self.product)
        self.assertEqual(first.quantity, 2)
        self.assertEqual(first.unit_price, Decimal("15.00"))
        self.assertEqual(first.product_title, "Portal <Two>")
        self.assertEqual(first.line_total, Decimal("30.00"))
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(LicenseKey.objects.filter(order__isnull=False).exists())

    def test_inactive_product_preserves_cart_and_creates_no_order(self):
        self.add()
        self.product.is_active = False
        self.product.save(update_fields=("is_active",))
        response = self.client.post("/api/cart/checkout/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CartItem.objects.filter(cart__user=self.user).exists())
        self.assertFalse(Order.objects.exists())

    @patch("apps.carts.services.OrderItem.objects.bulk_create")
    def test_failure_rolls_back_order_and_preserves_cart(self, bulk_create):
        bulk_create.side_effect = RuntimeError("database failure")
        self.add()
        with self.assertRaises(RuntimeError):
            self.client.post("/api/cart/checkout/")
        self.assertTrue(CartItem.objects.filter(cart__user=self.user).exists())
        self.assertFalse(Order.objects.exists())

    def test_rapid_repeated_checkout_creates_only_one_order(self):
        self.add()
        first = self.client.post("/api/cart/checkout/")
        second = self.client.post("/api/cart/checkout/")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Order.objects.count(), 1)


class CartConstraintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="constraints@example.com")
        self.platform = Platform.objects.create(name="Steam", slug="steam-constraints")
        self.product = Product.objects.create(
            title="Game",
            slug="game-constraints",
            price=Decimal("1.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )
        self.cart = Cart.objects.create(user=self.user)

    def test_database_enforces_one_cart_per_user(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cart.objects.create(user=self.user)

    def test_database_enforces_unique_product_and_quantity_bounds(self):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=self.cart, product=self.product, quantity=2)
        for quantity in (0, 100):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CartItem.objects.create(
                    cart=self.cart,
                    product=Product.objects.create(
                        title=f"Game {quantity}",
                        slug=f"game-{quantity}",
                        price=Decimal("1.00"),
                        product_type=Product.ProductType.GAME,
                        platform=self.platform,
                    ),
                    quantity=quantity,
                )

    def test_order_item_constraints(self):
        order = Order.objects.create(user=self.user, email=self.user.email)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_title=self.product.title,
            quantity=1,
            unit_price=self.product.price,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderItem.objects.create(
                order=order,
                product=self.product,
                product_title=self.product.title,
                quantity=1,
                unit_price=self.product.price,
            )


@skipUnlessDBFeature("has_select_for_update")
class CartConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(email="concurrent@example.com")
        self.platform = Platform.objects.create(
            name="Concurrent Steam", slug="concurrent-steam"
        )
        self.product = Product.objects.create(
            title="Concurrent Game",
            slug="concurrent-game",
            price=Decimal("10.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )
        self.cart = Cart.objects.create(user=self.user)
        self.item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=1,
        )

    def _run_pair(self, first, second):
        barrier = Barrier(2)

        def run(operation):
            close_old_connections()
            try:
                user = User.objects.get(pk=self.user.pk)
                barrier.wait()
                return operation(user)
            except (EmptyCartError, CartItemNotFoundError) as error:
                return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run, operation) for operation in (first, second)]
            return [future.result(timeout=10) for future in futures]

    def test_checkout_versus_checkout_creates_exactly_one_order(self):
        results = self._run_pair(checkout_cart, checkout_cart)

        self.assertEqual(sum(isinstance(result, Order) for result in results), 1)
        self.assertEqual(sum(isinstance(result, EmptyCartError) for result in results), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertFalse(CartItem.objects.exists())

    def test_quantity_update_versus_checkout_has_no_500_or_lost_state(self):
        results = self._run_pair(
            lambda user: set_cart_item_quantity(user, self.item.pk, 3),
            checkout_cart,
        )

        self.assertEqual(Order.objects.count(), 1)
        order_quantity = OrderItem.objects.get(order=Order.objects.get()).quantity
        self.assertIn(order_quantity, (1, 3))
        if order_quantity == 1:
            self.assertTrue(
                any(isinstance(result, CartItemNotFoundError) for result in results)
            )

    def test_add_item_versus_checkout_does_not_lose_quantity(self):
        self._run_pair(
            lambda user: add_cart_item(user, self.product.pk, 1),
            checkout_cart,
        )

        ordered_quantity = sum(
            OrderItem.objects.values_list("quantity", flat=True),
            start=0,
        )
        cart_quantity = sum(
            CartItem.objects.values_list("quantity", flat=True),
            start=0,
        )
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(ordered_quantity + cart_quantity, 2)
