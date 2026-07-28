from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import LicenseAssignment, Order, OrderItem, Payment
from apps.orders.payment_services import create_payment
from apps.orders.services import complete_payment, pay_order
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import LocalConfirmation, LocalPaymentProvider
from apps.payments.webhooks import (
    StripeCheckoutEventType,
    StripeCheckoutSession,
    StripeWebhookResult,
    process_stripe_webhook,
)


@override_settings(PAYMENT_PROVIDER="stripe")
class OrderServiceTests(TestCase):
    checkout_session_id = "cs_test_order_service"
    checkout_url = "https://checkout.stripe.com/c/pay/cs_test_order_service"

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

        stripe_client_patcher = patch(
            "apps.payments.providers.stripe.StripeClient"
        )
        self.addCleanup(stripe_client_patcher.stop)
        stripe_client = stripe_client_patcher.start().return_value
        self.create_checkout_session = (
            stripe_client.v1.checkout.sessions.create
        )
        self.create_checkout_session.return_value = SimpleNamespace(
            id=self.checkout_session_id,
            url=self.checkout_url,
        )

    def start_checkout(self, order):
        payment = create_payment(order)
        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertEqual(payment.provider, "stripe")
        self.assertEqual(payment.transaction_id, self.checkout_session_id)
        self.assertEqual(payment.checkout_url, self.checkout_url)
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )
        return payment

    def complete_checkout(self, payment):
        process_stripe_webhook(
            StripeWebhookResult(
                event_id=f"evt_test_order_service_{payment.id}",
                event_type=StripeCheckoutEventType.COMPLETED,
                checkout_session=StripeCheckoutSession(
                    id=payment.transaction_id,
                    local_payment_id=str(payment.id),
                ),
            )
        )

    def test_checkout_webhook_assigns_license_key(self):

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
            payment = self.start_checkout(order)
            self.complete_checkout(payment)

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
        assignment = LicenseAssignment.objects.get(
            license_key=self.license_key,
        )
        self.assertEqual(assignment.order_item.order, order)
        self.assertEqual(assignment.order_item.product, self.product)

        self.assertEqual(
            self.license_key.status,
            LicenseKey.Status.SOLD,
        )
        dispatch_email.assert_called_once_with(order.id)

    def test_complete_payment_is_idempotent(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.PENDING,
            amount=Decimal("59.99"),
            provider="local",
            transaction_id="local-pay-idempotent",
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            first = complete_payment(payment.id)
        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as duplicate_dispatch,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            second = complete_payment(payment.id)

        self.assertFalse(first.already_completed)
        self.assertTrue(second.already_completed)
        self.assertEqual(second.order.id, order.id)
        self.assertEqual(
            LicenseAssignment.objects.filter(
                order_item__order=order,
            ).count(),
            1,
        )
        dispatch_email.assert_called_once_with(order.id)
        duplicate_dispatch.assert_not_called()
        self.assertEqual(callbacks, [])

    def test_complete_payment_uses_one_paid_timestamp(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.PENDING,
            amount=Decimal("59.99"),
        )
        paid_at = timezone.now()

        with patch(
            "apps.orders.services.timezone.now",
            return_value=paid_at,
        ):
            complete_payment(payment.id)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.paid_at, paid_at)
        self.assertEqual(payment.paid_at, paid_at)
        self.assertEqual(self.license_key.sold_at, paid_at)

    def test_pay_order_reuses_created_payment(self):
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.CREATED,
            amount=Decimal("59.99"),
        )

        pay_order(order.id, provider=LocalPaymentProvider())

        payment.refresh_from_db()
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.provider, "local")
        self.assertTrue(payment.transaction_id.startswith("local-pay-"))

    @override_settings(PAYMENT_PROVIDER="changed-default")
    def test_existing_transaction_uses_its_stored_provider(self):
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.CREATED,
            amount=Decimal("59.99"),
            provider="local",
            transaction_id="local-pay-existing",
        )

        pay_order(order.id)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_matching_injected_provider_confirms_existing_transaction(self):
        class RecordingProvider:
            name = "recording"

            def __init__(self):
                self.confirmed = []

            def create_payment(self, request):
                raise AssertionError("not called")

            def confirm_payment(self, external_id):
                self.confirmed.append(external_id)
                return LocalPaymentProvider().confirm_payment(
                    "local-pay-recording"
                )

        provider = RecordingProvider()
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        Payment.objects.create(
            order=order,
            status=Payment.Status.CREATED,
            amount=Decimal("59.99"),
            provider=provider.name,
            transaction_id="recording-payment-1",
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.captureOnCommitCallbacks(execute=True),
        ):
            pay_order(order.id, provider=provider)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(provider.confirmed, ["recording-payment-1"])
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.license_key, self.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        dispatch_email.assert_called_once_with(order.id)

    def test_mismatched_injected_provider_is_rejected_before_confirmation(self):
        class UnexpectedProvider:
            name = "other"

            def create_payment(self, request):
                raise AssertionError("not called")

            def confirm_payment(self, external_id):
                raise AssertionError("not called")

        order, payment = self._existing_payment(provider="local")

        self._assert_provider_configuration_failure_preserves_state(
            order,
            payment,
            provider=UnexpectedProvider(),
        )

    def test_existing_transaction_without_provider_fails_safely(self):
        order, payment = self._existing_payment(provider="")

        self._assert_provider_configuration_failure_preserves_state(
            order,
            payment,
        )

    def test_unsupported_stored_provider_fails_safely(self):
        order, payment = self._existing_payment(
            provider="private-provider-name"
        )

        error = self._assert_provider_configuration_failure_preserves_state(
            order,
            payment,
        )

        self.assertNotIn("private-provider-name", str(error))
        self.assertNotIn("existing-transaction-secret", str(error))

    def _existing_payment(self, *, provider):
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.CREATED,
            amount=Decimal("59.99"),
            provider=provider,
            transaction_id="existing-transaction-secret",
        )
        return order, payment

    def _assert_provider_configuration_failure_preserves_state(
        self,
        order,
        payment,
        *,
        provider=None,
    ):
        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.assertRaisesMessage(
                OrderPaymentError,
                "Payment provider configuration is invalid",
            ) as error:
                pay_order(order.id, provider=provider)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.license_key)
        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertEqual(
            self.license_key.status,
            LicenseKey.Status.AVAILABLE,
        )
        dispatch_email.assert_not_called()
        return error.exception

    def test_rejected_provider_marks_payment_failed_without_fulfilment(self):
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        provider = LocalPaymentProvider(
            confirmation=LocalConfirmation.REJECT
        )

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.assertRaisesMessage(
                OrderPaymentError,
                "Payment was rejected",
            ),
        ):
            pay_order(order.id, provider=provider)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        dispatch_email.assert_not_called()

    def test_provider_exception_is_safe_and_rolls_back_local_state(self):
        class FailingProvider:
            name = "failing"

            def create_payment(self, request):
                raise PaymentProviderError("credential-like private detail")

            def confirm_payment(self, external_id):
                raise AssertionError("not called")

        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Payment provider could not confirm payment",
        ) as error:
            pay_order(order.id, provider=FailingProvider())

        self.assertNotIn("private detail", str(error.exception))
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.license_key.refresh_from_db()
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)

    def test_email_is_dispatched_only_after_payment_transaction_commits(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        payment = self.start_checkout(order)
        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.complete_checkout(payment)
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

        payment = self.start_checkout(order)
        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.assertRaisesMessage(RuntimeError, "force rollback"):
                with transaction.atomic():
                    self.complete_checkout(payment)
                    raise RuntimeError("force rollback")

        dispatch_email.assert_not_called()
        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)

    def test_broker_failure_after_commit_does_not_corrupt_completed_payment(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        payment = self.start_checkout(order)
        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay",
                side_effect=OperationalError("broker unavailable"),
            ),
            self.assertLogs("apps.orders.services", level="ERROR") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.complete_checkout(payment)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.license_key, self.license_key)
        self.assertEqual(self.license_key.status, LicenseKey.Status.SOLD)
        self.assertEqual(payment.status, Payment.Status.PAID)
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

        payment = create_payment(order)
        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as dispatch_email,
            self.assertRaisesMessage(OrderPaymentError, "No keys available"),
        ):
            self.complete_checkout(payment)

        dispatch_email.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)

    def test_duplicate_checkout_webhook_does_not_schedule_another_email(self):
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
            payment = self.start_checkout(order)
            self.complete_checkout(payment)
        dispatch_email.assert_called_once_with(order.id)
        self.assertEqual(
            LicenseAssignment.objects.filter(
                license_key=self.license_key,
            ).count(),
            1,
        )
        dispatch_email.reset_mock()

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as duplicate_dispatch,
        ):
            self.complete_checkout(payment)

        duplicate_dispatch.assert_not_called()
        self.assertEqual(
            LicenseAssignment.objects.filter(
                license_key=self.license_key,
            ).count(),
            1,
        )

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

    def test_checkout_webhook_persists_completed_sale_fields(self):
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
            payment = self.start_checkout(order)
            self.complete_checkout(payment)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        payment.refresh_from_db()

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
        payment = self.start_checkout(order)
        self.complete_checkout(payment)
        order.refresh_from_db()
        payment.refresh_from_db()

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
            create_payment(order)

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
            create_payment(order)

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

        payment = create_payment(order)
        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            self.complete_checkout(payment)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.price_paid)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)

    def test_checkout_webhook_fulfils_every_item_and_quantity(self):
        second_product = Product.objects.create(
            title="The Witcher 3",
            slug="the-witcher-3",
            price=Decimal("29.99"),
            product_type="GAME",
            platform=self.platform,
        )
        extra_keys = [
            LicenseKey.objects.create(
                product=self.product,
                value="TEST-KEY-456",
            ),
            LicenseKey.objects.create(
                product=second_product,
                value="WITCHER-KEY-123",
            ),
        ]
        order = Order.objects.create(
            product=None,
            email="cart@test.com",
            source=Order.Source.CART,
            total_price=Decimal("149.97"),
        )
        first_item = OrderItem.objects.create(
            order=order,
            product=self.product,
            product_title=self.product.title,
            quantity=2,
            unit_price=Decimal("59.99"),
        )
        second_item = OrderItem.objects.create(
            order=order,
            product=second_product,
            product_title=second_product.title,
            quantity=1,
            unit_price=Decimal("29.99"),
        )

        payment = self.start_checkout(order)
        self.complete_checkout(payment)

        order.refresh_from_db()
        assignments = LicenseAssignment.objects.filter(
            order_item__order=order
        )
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIsNone(order.license_key)
        self.assertEqual(assignments.count(), 3)
        self.assertEqual(
            assignments.filter(order_item=first_item).count(),
            2,
        )
        self.assertEqual(
            assignments.filter(order_item=second_item).count(),
            1,
        )
        for license_key in [self.license_key, *extra_keys]:
            license_key.refresh_from_db()
            self.assertEqual(license_key.status, LicenseKey.Status.SOLD)

        self.complete_checkout(payment)

        self.assertEqual(
            LicenseAssignment.objects.filter(order_item__order=order).count(),
            3,
        )

    def test_insufficient_keys_for_one_item_rolls_back_all_fulfilment(self):
        second_product = Product.objects.create(
            title="The Witcher 3",
            slug="the-witcher-3",
            price=Decimal("29.99"),
            product_type="GAME",
            platform=self.platform,
        )
        order = Order.objects.create(
            product=None,
            email="cart@test.com",
            source=Order.Source.CART,
            total_price=Decimal("89.98"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_title=self.product.title,
            quantity=1,
            unit_price=Decimal("59.99"),
        )
        OrderItem.objects.create(
            order=order,
            product=second_product,
            product_title=second_product.title,
            quantity=1,
            unit_price=Decimal("29.99"),
        )

        payment = self.start_checkout(order)
        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            self.complete_checkout(payment)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)
