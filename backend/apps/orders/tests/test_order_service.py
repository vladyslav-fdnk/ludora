from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import Order, Payment
from apps.orders.services import pay_order


class OrderServiceTests(TestCase):
    def setUp(self):
        self.platform = Platform.objects.create(
            name="Steam",
        )

        self.product = Product.objects.create(
            title="Cyberpunk 2077",
            slug="cyberpunk-2077",
            price=59.99,
            product_type="GAME",
            platform=self.platform,
        )

        self.license_key = LicenseKey.objects.create(
            product=self.product,
            value="TEST-KEY-123",
        )

    def test_pay_order_assigns_license_key(self):

        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()

        self.assertEqual(
            order.status,
            Order.Status.PAID,
        )

        self.assertEqual(
            order.license_key,
            self.license_key,
        )

        self.assertEqual(
            self.license_key.status,
            LicenseKey.Status.SOLD,
        )
        dispatch_email.assert_called_once_with(order.id)

    def test_email_is_dispatched_only_after_payment_transaction_commits(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                pay_order(order.id)
                dispatch_email.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            dispatch_email.assert_called_once_with(order.id)

    def test_rolled_back_payment_does_not_dispatch_email(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.assertRaisesMessage(RuntimeError, "force rollback"):
                with transaction.atomic():
                    pay_order(order.id)
                    raise RuntimeError("force rollback")

        dispatch_email.assert_not_called()
        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)

    def test_broker_failure_after_commit_does_not_corrupt_completed_payment(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay",
                side_effect=OperationalError("broker unavailable"),
            ),
            self.assertLogs("apps.orders.services", level="ERROR") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            paid_order = pay_order(order.id)

        paid_order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(paid_order.status, Order.Status.PAID)
        self.assertEqual(paid_order.license_key, self.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        self.assertTrue(
            Payment.objects.filter(
                order=paid_order,
                status=Payment.Status.PAID,
            ).exists()
        )
        log_output = "\n".join(logs.output)
        self.assertNotIn(self.license_key.value, log_output)
        self.assertNotIn(order.email, log_output)

    def test_insufficient_inventory_does_not_schedule_email(self):
        self.license_key.delete()
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.assertRaisesMessage(OrderPaymentError, "No keys available"),
        ):
            pay_order(order.id)

        dispatch_email.assert_not_called()

    def test_duplicate_completed_payment_does_not_schedule_another_email(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            pay_order(order.id)
        dispatch_email.assert_called_once_with(order.id)
        dispatch_email.reset_mock()

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as duplicate_dispatch,
            self.assertRaisesMessage(OrderPaymentError, "Already paid"),
        ):
            pay_order(order.id)

        duplicate_dispatch.assert_not_called()

    def test_cannot_pay_already_paid_order(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            status=Order.Status.PAID,
            total_price=Decimal("59.99"),
        )

        with self.assertRaises(OrderPaymentError) as error:
            pay_order(order.id)

        self.assertEqual(
            str(error.exception),
            "Already paid",
        )

    def test_pay_order_persists_completed_sale_fields(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )
        paid_at = timezone.now()

        with patch(
            "apps.orders.services.timezone.now",
            return_value=paid_at,
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        payment = Payment.objects.get(
            order=order,
        )

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.price_paid, Decimal("59.99"))
        self.assertEqual(order.paid_at, paid_at)
        self.assertEqual(order.license_key, self.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        self.assertEqual(self.license_key.sold_at, paid_at)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.amount, Decimal("59.99"))
        self.assertEqual(payment.paid_at, paid_at)

    def test_payment_uses_order_total_after_product_price_changes(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        self.product.price = Decimal("79.99")
        self.product.save(update_fields=("price",))
        pay_order(order.id)
        order.refresh_from_db()
        payment = Payment.objects.get(order=order)

        self.assertEqual(order.price_paid, Decimal("59.99"))
        self.assertEqual(payment.amount, Decimal("59.99"))
        self.assertEqual(order.product.price, Decimal("79.99"))

    def test_legacy_order_without_total_is_rejected_explicitly(self):
        order = Order.objects.create(
            product=self.product,
            email="legacy@test.com",
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Order has no authoritative total and requires manual review",
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.price_paid)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(Payment.objects.exists())

    def test_missing_product_is_rejected_before_side_effects(self):
        order = Order.objects.create(
            product=None,
            email="legacy@test.com",
            total_price=Decimal("59.99"),
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Order has no product reference and requires manual review",
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(Payment.objects.exists())

    def test_no_license_key_preserves_order_and_payment_state(self):
        self.license_key.delete()
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            pay_order(order.id)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.price_paid)
        self.assertFalse(Payment.objects.exists())

    def test_cart_order_is_rejected_by_direct_payment_flow(self):
        order = Order.objects.create(
            product=None,
            email="cart@test.com",
            source=Order.Source.CART,
            total_price=Decimal("59.99"),
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Cart orders are not payable in this stage",
        ):
            pay_order(order.id)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(Payment.objects.exists())
