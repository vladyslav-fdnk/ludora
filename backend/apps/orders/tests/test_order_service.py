from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

from django.db import close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import LicenseAssignment, Order, OrderItem, Payment
from apps.orders.payment_services import create_payment
from apps.orders.services import (
    complete_payment,
    pay_order,
    release_order_license_reservation,
    reserve_order_licenses,
    terminate_payment,
)
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
        assignments = list(
            LicenseAssignment.objects.filter(order_item__order=order)
            .select_related("order_item", "license_key")
            .order_by("id")
        )
        self.assertEqual(
            len(assignments),
            sum(order.items.values_list("quantity", flat=True)),
        )
        for assignment in assignments:
            self.assertEqual(
                assignment.license_key.product_id,
                assignment.order_item.product_id,
            )
            self.assertEqual(
                assignment.license_key.status,
                LicenseKey.Status.RESERVED,
            )
            self.assertIsNone(assignment.license_key.sold_at)
        return payment

    def complete_checkout(self, payment):
        process_stripe_webhook(
            StripeWebhookResult(
                event_id=f"evt_test_order_service_{payment.id}",
                event_type=StripeCheckoutEventType.COMPLETED,
                checkout_session=StripeCheckoutSession(
                    id=payment.transaction_id,
                    local_payment_id=str(payment.id),
                    payment_status="paid",
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
            reserved_assignment = LicenseAssignment.objects.get(
                order_item__order=order,
            )
            self.assertEqual(
                reserved_assignment.license_key.status,
                LicenseKey.Status.RESERVED,
            )
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
        self.assertEqual(assignment.id, reserved_assignment.id)
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

    @override_settings(PAYMENT_PROVIDER="unsupported-default")
    def test_invalid_default_provider_uses_public_exception_contract(self):
        order = Order.objects.create(
            product=self.product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Payment provider configuration is invalid",
        ):
            pay_order(order.id)

        self.assertFalse(Payment.objects.filter(order=order).exists())

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

    def test_rejected_provider_marks_payment_failed_and_releases_reservation(self):
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
        self.assertFalse(
            LicenseAssignment.objects.filter(
                license_key=self.license_key,
            ).exists()
        )
        self.assertIsNone(self.license_key.sold_at)
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
        reserved_assignment = LicenseAssignment.objects.get(
            order_item__order=order,
        )
        with patch(
            "apps.orders.tasks.send_order_confirmation_email.delay"
        ) as dispatch_email:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.complete_checkout(payment)
                dispatch_email.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            dispatch_email.assert_called_once_with(order.id)
        assignment = LicenseAssignment.objects.get(order_item__order=order)
        self.assertEqual(assignment.id, reserved_assignment.id)
        self.assertEqual(assignment.license_key.status, LicenseKey.Status.SOLD)

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
        self.assertEqual(self.license_key.status, LicenseKey.Status.RESERVED)
        assignment = LicenseAssignment.objects.get(
            license_key=self.license_key,
        )
        self.assertEqual(assignment.order_item.order, order)
        self.assertIsNone(self.license_key.sold_at)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CREATED)

    def test_broker_failure_after_commit_does_not_corrupt_completed_payment(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
            total_price=Decimal("59.99"),
        )

        payment = self.start_checkout(order)
        reserved_assignment = LicenseAssignment.objects.get(
            order_item__order=order,
        )
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
        assignment = LicenseAssignment.objects.get(order_item__order=order)
        self.assertEqual(assignment.id, reserved_assignment.id)
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
            create_payment(order)

        dispatch_email.assert_not_called()
        self.create_checkout_session.assert_not_called()
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )

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
            reserved_assignment = LicenseAssignment.objects.get(
                order_item__order=order,
            )
            self.complete_checkout(payment)
        dispatch_email.assert_called_once_with(order.id)
        assignment = LicenseAssignment.objects.get(
            license_key=self.license_key,
        )
        self.assertEqual(assignment.id, reserved_assignment.id)
        dispatch_email.reset_mock()

        with (
            patch(
                "apps.orders.tasks.send_order_confirmation_email.delay"
            ) as duplicate_dispatch,
        ):
            self.complete_checkout(payment)

        duplicate_dispatch.assert_not_called()
        duplicate_assignment = LicenseAssignment.objects.get(
            license_key=self.license_key,
        )
        self.assertEqual(duplicate_assignment.id, reserved_assignment.id)
        self.assertEqual(
            duplicate_assignment.license_key.status,
            LicenseKey.Status.SOLD,
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
            reserved_assignment = LicenseAssignment.objects.get(
                order_item__order=order,
            )
            self.assertIsNone(reserved_assignment.license_key.sold_at)
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
        assignment = LicenseAssignment.objects.get(order_item__order=order)
        self.assertEqual(assignment.id, reserved_assignment.id)
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
        reserved_assignment = LicenseAssignment.objects.get(
            order_item__order=order,
        )
        self.complete_checkout(payment)
        order.refresh_from_db()
        payment.refresh_from_db()
        assignment = LicenseAssignment.objects.get(order_item__order=order)

        self.assertEqual(order.price_paid, Decimal("59.99"))
        self.assertEqual(payment.amount, Decimal("59.99"))
        self.assertEqual(order.product.price, Decimal("79.99"))
        self.assertEqual(assignment.id, reserved_assignment.id)
        self.assertEqual(assignment.license_key.status, LicenseKey.Status.SOLD)

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

        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            create_payment(order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertIsNone(order.price_paid)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )
        self.create_checkout_session.assert_not_called()

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
        reserved_assignments = list(
            LicenseAssignment.objects.filter(order_item__order=order)
            .select_related("license_key")
            .order_by("id")
        )
        reserved_assignment_ids = [
            assignment.id for assignment in reserved_assignments
        ]
        reserved_key_ids = [
            assignment.license_key_id for assignment in reserved_assignments
        ]
        self.assertEqual(len(reserved_assignments), 3)
        self.assertEqual(
            sum(
                assignment.order_item_id == first_item.id
                for assignment in reserved_assignments
            ),
            2,
        )
        self.assertEqual(
            sum(
                assignment.order_item_id == second_item.id
                for assignment in reserved_assignments
            ),
            1,
        )
        self.assertTrue(
            all(
                assignment.license_key.status
                == LicenseKey.Status.RESERVED
                for assignment in reserved_assignments
            )
        )
        self.complete_checkout(payment)

        order.refresh_from_db()
        assignments = list(
            LicenseAssignment.objects.filter(order_item__order=order)
            .select_related("license_key")
            .order_by("id")
        )
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIsNone(order.license_key)
        self.assertEqual(
            [assignment.id for assignment in assignments],
            reserved_assignment_ids,
        )
        self.assertEqual(
            [assignment.license_key_id for assignment in assignments],
            reserved_key_ids,
        )
        self.assertTrue(
            all(
                assignment.license_key.status == LicenseKey.Status.SOLD
                for assignment in assignments
            )
        )
        for license_key in [self.license_key, *extra_keys]:
            license_key.refresh_from_db()
            self.assertEqual(license_key.status, LicenseKey.Status.SOLD)

        self.complete_checkout(payment)

        self.assertEqual(
            list(
                LicenseAssignment.objects.filter(order_item__order=order)
                .order_by("id")
                .values_list("id", flat=True)
            ),
            reserved_assignment_ids,
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

        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            create_payment(order)

        order.refresh_from_db()
        self.license_key.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(self.license_key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.create_checkout_session.assert_not_called()


class LicenseReservationTests(TestCase):
    def setUp(self):
        self.platform = Platform.objects.create(name="Steam")
        self.product = Product.objects.create(
            title="Reservation Game",
            slug="reservation-game",
            price=Decimal("20.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )

    def create_order(self, *, product=None, quantity=1):
        product = product or self.product
        order = Order.objects.create(
            product=None,
            email="buyer@test.invalid",
            source=Order.Source.CART,
            total_price=product.price * quantity,
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            product_title=product.title,
            quantity=quantity,
            unit_price=product.price,
        )
        return order, item

    def create_keys(self, product, count, *, prefix="KEY"):
        return [
            LicenseKey.objects.create(
                product=product,
                value=f"{prefix}-{index}",
            )
            for index in range(count)
        ]

    def reservation_state(self, order, keys):
        assignments = list(
            LicenseAssignment.objects.filter(order_item__order=order)
            .order_by("id")
            .values_list("id", "order_item_id", "license_key_id")
        )
        key_state = list(
            LicenseKey.objects.filter(id__in=[key.id for key in keys])
            .order_by("id")
            .values_list("id", "status", "product_id", "sold_at")
        )
        return assignments, key_state

    def test_reserves_complete_single_item_without_payment(self):
        order, item = self.create_order(quantity=2)
        keys = self.create_keys(self.product, 2)

        assignments = reserve_order_licenses(order.id)

        self.assertEqual(len(assignments), 2)
        self.assertEqual(
            {assignment.order_item_id for assignment in assignments},
            {item.id},
        )
        for key in keys:
            key.refresh_from_db()
            self.assertEqual(key.status, LicenseKey.Status.RESERVED)
            self.assertIsNone(key.sold_at)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_reserves_every_product_and_quantity_atomically(self):
        second_product = Product.objects.create(
            title="Second Reservation Game",
            slug="second-reservation-game",
            price=Decimal("15.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )
        order, first_item = self.create_order(quantity=2)
        second_item = OrderItem.objects.create(
            order=order,
            product=second_product,
            product_title=second_product.title,
            quantity=1,
            unit_price=second_product.price,
        )
        order.total_price = Decimal("55.00")
        order.save(update_fields=("total_price",))
        keys = [
            *self.create_keys(self.product, 2, prefix="FIRST"),
            *self.create_keys(second_product, 1, prefix="SECOND"),
        ]

        reserve_order_licenses(order.id)

        self.assertEqual(
            LicenseAssignment.objects.filter(order_item=first_item).count(),
            2,
        )
        self.assertEqual(
            LicenseAssignment.objects.filter(order_item=second_item).count(),
            1,
        )
        for assignment in LicenseAssignment.objects.filter(order_item__order=order).select_related(
            "order_item", "license_key"
        ):
            self.assertEqual(
                assignment.order_item.product_id,
                assignment.license_key.product_id,
            )
        self.assertEqual(
            LicenseKey.objects.filter(
                id__in=[key.id for key in keys],
                status=LicenseKey.Status.RESERVED,
            ).count(),
            3,
        )

    def test_insufficient_later_item_rolls_back_entire_reservation(self):
        second_product = Product.objects.create(
            title="Unavailable Game",
            slug="unavailable-game",
            price=Decimal("10.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )
        order, _ = self.create_order()
        OrderItem.objects.create(
            order=order,
            product=second_product,
            product_title=second_product.title,
            quantity=1,
            unit_price=second_product.price,
        )
        key = self.create_keys(self.product, 1)[0]

        with self.assertRaisesMessage(OrderPaymentError, "No keys available"):
            reserve_order_licenses(order.id)

        key.refresh_from_db()
        self.assertEqual(key.status, LicenseKey.Status.AVAILABLE)
        self.assertFalse(LicenseAssignment.objects.filter(order_item__order=order).exists())

    def test_complete_reservation_is_reused_without_more_allocation(self):
        order, _ = self.create_order()
        keys = self.create_keys(self.product, 2)
        first = reserve_order_licenses(order.id)

        second = reserve_order_licenses(order.id)

        self.assertEqual(
            [assignment.id for assignment in second],
            [assignment.id for assignment in first],
        )
        keys[1].refresh_from_db()
        self.assertEqual(keys[1].status, LicenseKey.Status.AVAILABLE)
        self.assertEqual(
            LicenseAssignment.objects.filter(order_item__order=order).count(),
            1,
        )

    def test_legacy_direct_order_is_normalized_for_reservation(self):
        order = Order.objects.create(
            product=self.product,
            email="legacy@test.invalid",
            total_price=self.product.price,
        )
        key = self.create_keys(self.product, 1)[0]

        assignments = reserve_order_licenses(order.id)

        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].order_item.order_id, order.id)
        key.refresh_from_db()
        self.assertEqual(key.status, LicenseKey.Status.RESERVED)
        order.refresh_from_db()
        self.assertIsNone(order.license_key_id)

    def test_paid_and_unusable_orders_cannot_be_reserved(self):
        paid_order, _ = self.create_order()
        paid_order.status = Order.Status.PAID
        paid_order.save(update_fields=("status",))
        unusable_order = Order.objects.create(
            product=None,
            email="invalid@test.invalid",
            total_price=Decimal("1.00"),
        )

        with self.assertRaisesMessage(
            OrderPaymentError,
            "Paid orders cannot reserve licenses",
        ):
            reserve_order_licenses(paid_order.id)
        with self.assertRaisesMessage(
            OrderPaymentError,
            "Order has no product reference and requires manual review",
        ):
            reserve_order_licenses(unusable_order.id)

    def test_inconsistent_existing_reservations_are_rejected_unchanged(self):
        cases = ("partial", "over-complete", "wrong-product", "wrong-state")
        for case in cases:
            with self.subTest(case=case):
                order, item = self.create_order(quantity=2)
                keys = self.create_keys(
                    self.product,
                    3,
                    prefix=case,
                )
                assigned_keys = keys[:1] if case == "partial" else keys[:2]
                if case == "over-complete":
                    assigned_keys = keys
                if case == "wrong-product":
                    other_product = Product.objects.create(
                        title=f"Other {case}",
                        slug=f"other-{case}",
                        price=Decimal("1.00"),
                        product_type=Product.ProductType.GAME,
                        platform=self.platform,
                    )
                    assigned_keys[0].product = other_product
                    assigned_keys[0].save(update_fields=("product",))
                for key in assigned_keys:
                    key.status = LicenseKey.Status.RESERVED
                    key.save(update_fields=("status",))
                    LicenseAssignment.objects.create(
                        order_item=item,
                        license_key=key,
                    )
                if case == "wrong-state":
                    assigned_keys[0].status = LicenseKey.Status.SOLD
                    assigned_keys[0].sold_at = timezone.now()
                    assigned_keys[0].save(update_fields=("status", "sold_at"))

                before = self.reservation_state(order, keys)

                with self.assertRaisesMessage(
                    OrderPaymentError,
                    "Order reservation is inconsistent",
                ):
                    reserve_order_licenses(order.id)

                self.assertEqual(self.reservation_state(order, keys), before)

    def test_assignment_failure_rolls_back_complete_state_and_retry_succeeds(self):
        order, _ = self.create_order(quantity=2)
        keys = self.create_keys(self.product, 2)
        before = self.reservation_state(order, keys)

        with (
            patch.object(
                LicenseAssignment.objects,
                "bulk_create",
                side_effect=RuntimeError("assignment failed"),
            ),
            self.assertRaisesMessage(RuntimeError, "assignment failed"),
        ):
            reserve_order_licenses(order.id)

        self.assertEqual(self.reservation_state(order, keys), before)

        assignments = reserve_order_licenses(order.id)

        self.assertEqual(len(assignments), 2)
        self.assertEqual(
            {row[2] for row in self.reservation_state(order, keys)[0]},
            {key.id for key in keys},
        )

    def test_release_is_complete_scoped_and_idempotent(self):
        order, _ = self.create_order(quantity=2)
        other_order, _ = self.create_order()
        keys = self.create_keys(self.product, 3)
        reserve_order_licenses(order.id)
        reserve_order_licenses(other_order.id)

        released = release_order_license_reservation(order.id)
        repeated = release_order_license_reservation(order.id)

        self.assertEqual({key.id for key in released}, {keys[0].id, keys[1].id})
        self.assertEqual(repeated, [])
        self.assertFalse(LicenseAssignment.objects.filter(order_item__order=order).exists())
        self.assertEqual(
            LicenseAssignment.objects.filter(order_item__order=other_order).count(),
            1,
        )
        for key in keys[:2]:
            key.refresh_from_db()
            self.assertEqual(key.status, LicenseKey.Status.AVAILABLE)
            self.assertIsNone(key.sold_at)
        keys[2].refresh_from_db()
        self.assertEqual(keys[2].status, LicenseKey.Status.RESERVED)

    def test_unsuccessful_terminal_payments_release_reservations_idempotently(self):
        for status in (
            Payment.Status.FAILED,
            Payment.Status.CANCELLED,
            Payment.Status.EXPIRED,
        ):
            with self.subTest(status=status):
                order, _ = self.create_order()
                key = self.create_keys(
                    self.product,
                    1,
                    prefix=status,
                )[0]
                payment = Payment.objects.create(
                    order=order,
                    status=Payment.Status.PENDING,
                    amount=order.total_price,
                )
                reserve_order_licenses(order.id)

                terminate_payment(
                    order=order,
                    payment=payment,
                    status=status,
                )
                terminate_payment(
                    order=order,
                    payment=payment,
                    status=status,
                )

                payment.refresh_from_db()
                key.refresh_from_db()
                self.assertEqual(payment.status, status)
                self.assertEqual(key.status, LicenseKey.Status.AVAILABLE)
                self.assertFalse(
                    LicenseAssignment.objects.filter(
                        order_item__order=order,
                    ).exists()
                )

    def test_paid_payment_is_not_changed_or_released(self):
        order, _ = self.create_order()
        key = self.create_keys(self.product, 1, prefix="PAID")[0]
        payment = Payment.objects.create(
            order=order,
            status=Payment.Status.PENDING,
            amount=order.total_price,
        )
        reserve_order_licenses(order.id)
        complete_payment(payment.id)
        payment.refresh_from_db()

        terminate_payment(
            order=order,
            payment=payment,
            status=Payment.Status.FAILED,
        )

        payment.refresh_from_db()
        key.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(key.status, LicenseKey.Status.SOLD)
        self.assertTrue(
            LicenseAssignment.objects.filter(order_item__order=order).exists()
        )

    def test_release_rejects_paid_order_and_sold_inventory(self):
        paid_order, _ = self.create_order()
        paid_order.status = Order.Status.PAID
        paid_order.save(update_fields=("status",))
        with self.assertRaisesMessage(
            OrderPaymentError,
            "Paid orders cannot release licenses",
        ):
            release_order_license_reservation(paid_order.id)

        order, item = self.create_order()
        sold_key = self.create_keys(self.product, 1, prefix="SOLD")[0]
        sold_key.status = LicenseKey.Status.SOLD
        sold_key.sold_at = timezone.now()
        sold_key.save(update_fields=("status", "sold_at"))
        assignment = LicenseAssignment.objects.create(
            order_item=item,
            license_key=sold_key,
        )
        with self.assertRaisesMessage(
            OrderPaymentError,
            "Order reservation is inconsistent",
        ):
            release_order_license_reservation(order.id)

        sold_key.refresh_from_db()
        self.assertEqual(sold_key.status, LicenseKey.Status.SOLD)
        self.assertTrue(LicenseAssignment.objects.filter(id=assignment.id).exists())

    def test_assignment_deletion_failure_rolls_back_release_and_retry_succeeds(self):
        order, _ = self.create_order(quantity=2)
        keys = self.create_keys(self.product, 2)
        reserve_order_licenses(order.id)
        before = self.reservation_state(order, keys)

        with (
            patch(
                "django.db.models.query.QuerySet.delete",
                side_effect=RuntimeError("assignment deletion failed"),
            ),
            self.assertRaisesMessage(RuntimeError, "assignment deletion failed"),
        ):
            release_order_license_reservation(order.id)

        self.assertEqual(self.reservation_state(order, keys), before)

        released = release_order_license_reservation(order.id)

        self.assertEqual({key.id for key in released}, {key.id for key in keys})
        self.assertEqual(
            self.reservation_state(order, keys),
            (
                [],
                [
                    (key.id, LicenseKey.Status.AVAILABLE, key.product_id, None)
                    for key in keys
                ],
            ),
        )


class ConcurrentLicenseReservationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.platform = Platform.objects.create(name="Steam")
        self.product = Product.objects.create(
            title="Concurrent Game",
            slug="concurrent-game",
            price=Decimal("10.00"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )

    def create_order(self):
        order = Order.objects.create(
            product=None,
            email="buyer@test.invalid",
            source=Order.Source.CART,
            total_price=self.product.price,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            product_title=self.product.title,
            quantity=1,
            unit_price=self.product.price,
        )
        return order

    def run_concurrently(self, *operations):
        start = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                start.wait()
                return operation()
            except Exception as error:
                return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(run, operations))

    def test_same_order_reservations_converge_on_one_assignment(self):
        order = self.create_order()
        key = LicenseKey.objects.create(
            product=self.product,
            value="SAME-ORDER-KEY",
        )

        results = self.run_concurrently(
            lambda: reserve_order_licenses(order.id),
            lambda: reserve_order_licenses(order.id),
        )

        self.assertFalse([result for result in results if isinstance(result, Exception)])
        assignment = LicenseAssignment.objects.get(order_item__order=order)
        self.assertTrue(all(result[0].id == assignment.id for result in results))
        key.refresh_from_db()
        self.assertEqual(key.status, LicenseKey.Status.RESERVED)

    def test_competing_orders_cannot_reserve_the_same_limited_key(self):
        first_order = self.create_order()
        second_order = self.create_order()
        key = LicenseKey.objects.create(
            product=self.product,
            value="CONTENDED-KEY",
        )

        results = self.run_concurrently(
            lambda: reserve_order_licenses(first_order.id),
            lambda: reserve_order_licenses(second_order.id),
        )

        self.assertEqual(
            sum(not isinstance(result, Exception) for result in results),
            1,
        )
        self.assertEqual(
            sum(isinstance(result, OrderPaymentError) for result in results),
            1,
        )
        self.assertEqual(LicenseAssignment.objects.count(), 1)
        key.refresh_from_db()
        self.assertEqual(key.status, LicenseKey.Status.RESERVED)

    def test_different_orders_with_sufficient_inventory_both_reserve(self):
        first_order = self.create_order()
        second_order = self.create_order()
        for value in ("AVAILABLE-1", "AVAILABLE-2"):
            LicenseKey.objects.create(product=self.product, value=value)

        results = self.run_concurrently(
            lambda: reserve_order_licenses(first_order.id),
            lambda: reserve_order_licenses(second_order.id),
        )

        self.assertFalse([result for result in results if isinstance(result, Exception)])
        self.assertEqual(LicenseAssignment.objects.count(), 2)
        self.assertEqual(
            LicenseAssignment.objects.values("license_key_id").distinct().count(),
            2,
        )

    def test_simultaneous_reservation_and_release_leave_valid_state(self):
        order = self.create_order()
        key = LicenseKey.objects.create(
            product=self.product,
            value="RESERVE-RELEASE-KEY",
        )
        reserve_order_licenses(order.id)

        results = self.run_concurrently(
            lambda: reserve_order_licenses(order.id),
            lambda: release_order_license_reservation(order.id),
        )

        self.assertFalse([result for result in results if isinstance(result, Exception)])
        key.refresh_from_db()
        assignments = LicenseAssignment.objects.filter(order_item__order=order)
        if assignments.exists():
            self.assertEqual(assignments.count(), 1)
            self.assertEqual(key.status, LicenseKey.Status.RESERVED)
        else:
            self.assertEqual(key.status, LicenseKey.Status.AVAILABLE)

    def test_simultaneous_releases_are_scoped_and_idempotent(self):
        order = self.create_order()
        other_order = self.create_order()
        key = LicenseKey.objects.create(
            product=self.product,
            value="RELEASE-KEY",
        )
        other_key = LicenseKey.objects.create(
            product=self.product,
            value="OTHER-ORDER-KEY",
        )
        reserve_order_licenses(order.id)
        reserve_order_licenses(other_order.id)

        results = self.run_concurrently(
            lambda: release_order_license_reservation(order.id),
            lambda: release_order_license_reservation(order.id),
        )

        self.assertFalse([result for result in results if isinstance(result, Exception)])
        key.refresh_from_db()
        other_key.refresh_from_db()
        self.assertEqual(key.status, LicenseKey.Status.AVAILABLE)
        self.assertEqual(other_key.status, LicenseKey.Status.RESERVED)
        self.assertFalse(LicenseAssignment.objects.filter(order_item__order=order).exists())
        self.assertEqual(
            LicenseAssignment.objects.filter(order_item__order=other_order).count(),
            1,
        )


class ConcurrentPayOrderTests(TransactionTestCase):
    def test_calls_for_same_order_do_not_share_provisional_payment_state(self):
        platform = Platform.objects.create(name="Steam")
        product = Product.objects.create(
            title="Cyber Game",
            price=Decimal("59.99"),
            platform=platform,
        )
        LicenseKey.objects.create(product=product, value="TEST-KEY-123")
        order = Order.objects.create(
            product=product,
            email="buyer@test.invalid",
            total_price=Decimal("59.99"),
        )
        start = Barrier(2)
        concurrent_provider_call = Event()
        call_lock = Lock()
        provider = LocalPaymentProvider()
        create_call_count = 0

        class BlockingProvider:
            name = provider.name

            def create_payment(self, request):
                nonlocal create_call_count
                with call_lock:
                    create_call_count += 1
                    call_number = create_call_count
                if call_number == 1:
                    concurrent_provider_call.wait(timeout=1)
                else:
                    concurrent_provider_call.set()
                return provider.create_payment(request)

            def confirm_payment(self, external_id):
                return provider.confirm_payment(external_id)

        def attempt_payment():
            close_old_connections()
            try:
                start.wait()
                return pay_order(order.id, provider=BlockingProvider())
            except OrderPaymentError as error:
                return error
            finally:
                close_old_connections()

        with (
            patch("apps.orders.tasks.send_order_confirmation_email.delay"),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(executor.map(lambda _: attempt_payment(), range(2)))

        order.refresh_from_db()
        payment = Payment.objects.get(order=order)
        self.assertEqual(create_call_count, 1)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(
            [str(result) for result in results if isinstance(result, Exception)],
            ["Already paid"],
        )
