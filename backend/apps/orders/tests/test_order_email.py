import json
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.games.models import LicenseKey, Platform, Product
from apps.orders.emails import build_order_confirmation_email
from apps.orders.models import Order, OrderItem, Payment
from apps.orders.tasks import send_order_confirmation_email


class OrderEmailTestCase(TestCase):
    def setUp(self):
        self.platform = Platform.objects.create(name="Steam", slug="steam")
        self.product = Product.objects.create(
            title="Cyber Game",
            slug="cyber-game",
            price=Decimal("59.99"),
            product_type=Product.ProductType.GAME,
            platform=self.platform,
        )
        self.license_key = LicenseKey.objects.create(
            product=self.product,
            value="ASSIGNED-KEY-123",
            status=LicenseKey.Status.SOLD,
            sold_at=timezone.now(),
        )
        self.order = Order.objects.create(
            product=self.product,
            email="buyer@example.com",
            status=Order.Status.PAID,
            total_price=Decimal("59.99"),
            price_paid=Decimal("59.99"),
            license_key=self.license_key,
            paid_at=timezone.now(),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_title="Cyber Game",
            quantity=1,
            unit_price=Decimal("59.99"),
        )
        Payment.objects.create(
            order=self.order,
            status=Payment.Status.PAID,
            amount=Decimal("59.99"),
            paid_at=self.order.paid_at,
        )


class OrderEmailCompositionTests(OrderEmailTestCase):
    def test_confirmation_contains_only_relevant_order_details(self):
        unrelated_key = LicenseKey.objects.create(
            product=self.product,
            value="UNRELATED-KEY-999",
        )

        message = build_order_confirmation_email(self.order)

        self.assertEqual(message.to, ["buyer@example.com"])
        self.assertIn("order confirmation", message.subject.lower())
        self.assertIn(self.order.order_number, message.subject)
        self.assertIn(self.order.order_number, message.body)
        self.assertIn("Cyber Game", message.body)
        self.assertIn(self.license_key.value, message.body)
        self.assertIn("59.99", message.body)
        self.assertNotIn(unrelated_key.value, message.body)


class OrderEmailTaskTests(OrderEmailTestCase):
    def test_task_sends_exactly_one_email_for_eligible_order(self):
        with self.assertLogs("apps.orders.tasks", level="INFO") as logs:
            result = send_order_confirmation_email.apply(args=[self.order.pk]).get()

        self.assertEqual(result, {"order_id": self.order.pk, "status": "sent"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.license_key.value, "\n".join(logs.output))

    def test_task_safely_handles_missing_order(self):
        result = send_order_confirmation_email.apply(args=[999_999]).get()

        self.assertEqual(result, {"order_id": 999_999, "status": "missing"})
        self.assertEqual(mail.outbox, [])

    def test_task_does_not_send_for_ineligible_order(self):
        states = [
            (Order.Status.CREATED, Payment.Status.CREATED),
            (Order.Status.CREATED, Payment.Status.FAILED),
        ]

        for order_status, payment_status in states:
            with self.subTest(
                order_status=order_status,
                payment_status=payment_status,
            ):
                self.order.status = order_status
                self.order.save(update_fields=["status"])
                self.order.payments.update(status=payment_status)

                result = send_order_confirmation_email.apply(
                    args=[self.order.pk]
                ).get()

                self.assertEqual(
                    result,
                    {"order_id": self.order.pk, "status": "ineligible"},
                )
                self.assertEqual(mail.outbox, [])

    def test_task_payload_and_result_are_json_serializable(self):
        payload = {"order_id": self.order.pk}
        json.dumps(payload)

        result = send_order_confirmation_email.apply(kwargs=payload).get()

        self.assertEqual(json.loads(json.dumps(result))["status"], "sent")

    def test_delay_executes_eagerly_without_redis(self):
        result = send_order_confirmation_email.delay(self.order.pk)

        self.assertEqual(result.get()["status"], "sent")
        self.assertEqual(len(mail.outbox), 1)
