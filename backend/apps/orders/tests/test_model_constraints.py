from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.orders.models import Order, Payment


class PaymentConstraintTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            email="constraints@example.com",
            total_price=Decimal("10.00"),
        )

    def create_payment(self, status):
        return Payment.objects.create(
            order=self.order,
            status=status,
            amount=Decimal("10.00"),
        )

    def test_order_reservation_payment_attempt_is_nullable(self):
        self.assertIsNone(self.order.reservation_payment_attempt)

    def test_order_reservation_payment_attempt_protects_payment_from_deletion(self):
        payment = self.create_payment(Payment.Status.CREATED)
        self.order.reservation_payment_attempt = payment
        self.order.save(update_fields=("reservation_payment_attempt",))

        with self.assertRaises(ProtectedError):
            payment.delete()

        self.order.refresh_from_db()
        self.assertEqual(self.order.reservation_payment_attempt, payment)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_second_active_payment_for_order_is_rejected(self):
        for first_status, second_status in (
            (Payment.Status.CREATED, Payment.Status.CREATED),
            (Payment.Status.CREATED, Payment.Status.PENDING),
            (Payment.Status.PENDING, Payment.Status.CREATED),
            (Payment.Status.PENDING, Payment.Status.PENDING),
        ):
            with self.subTest(
                first_status=first_status,
                second_status=second_status,
            ):
                Payment.objects.all().delete()
                self.create_payment(first_status)

                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.create_payment(second_status)

    def test_multiple_terminal_payments_for_order_are_permitted(self):
        for status in (
            Payment.Status.PAID,
            Payment.Status.FAILED,
            Payment.Status.CANCELLED,
            Payment.Status.EXPIRED,
        ):
            self.create_payment(status)
            self.create_payment(status)

        self.assertEqual(self.order.payments.count(), 8)

    def test_active_payments_for_different_orders_are_permitted(self):
        other_order = Order.objects.create(
            email="other-constraints@example.com",
            total_price=Decimal("10.00"),
        )
        self.create_payment(Payment.Status.CREATED)

        Payment.objects.create(
            order=other_order,
            status=Payment.Status.CREATED,
            amount=Decimal("10.00"),
        )

        self.assertEqual(Payment.objects.count(), 2)
