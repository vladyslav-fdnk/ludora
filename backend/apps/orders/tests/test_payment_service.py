from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.games.models import Platform, Product
from apps.orders.exceptions import OrderPaymentError
from apps.orders.models import (
    Order,
    Payment,
)
from apps.orders.payment_services import create_payment


class PaymentServiceTests(TestCase):
    def setUp(self):

        self.platform = Platform.objects.create(name="Steam")

        self.product = Product.objects.create(
            title="Cyber Game",
            price=Decimal("59.99"),
            platform=self.platform,
        )

    def test_create_payment_for_order(self):
        order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

        payment = create_payment(order)

        self.assertEqual(
            payment.order,
            order,
        )

        self.assertEqual(
            payment.status,
            Payment.Status.CREATED,
        )

        self.assertEqual(
            payment.amount,
            Decimal("59.99"),
        )


class ConcurrentPaymentServiceTests(TransactionTestCase):
    def setUp(self):
        self.platform = Platform.objects.create(name="Steam")
        self.product = Product.objects.create(
            title="Cyber Game",
            price=Decimal("59.99"),
            platform=self.platform,
        )
        self.order = Order.objects.create(
            product=self.product,
            email="test@test.com",
        )

    def test_create_payment_reloads_and_locks_order(self):
        stale_order = Order.objects.get(pk=self.order.pk)
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PAID)

        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(
                OrderPaymentError,
                "Order already paid",
            ):
                create_payment(stale_order)

        order_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "orders_order"' in query["sql"]
        ]
        self.assertTrue(
            any("FOR UPDATE" in sql for sql in order_queries),
            order_queries,
        )
        self.assertFalse(Payment.objects.exists())

    def test_competing_attempts_create_only_one_active_payment(self):
        barrier = Barrier(2)

        def attempt_payment():
            close_old_connections()
            try:
                order = Order.objects.get(pk=self.order.pk)
                barrier.wait()
                return create_payment(order)
            except OrderPaymentError as error:
                return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt_payment(), range(2)))

        payments = Payment.objects.filter(
            order=self.order,
            status__in=[
                Payment.Status.CREATED,
                Payment.Status.PENDING,
            ],
        )
        self.assertEqual(payments.count(), 1)
        self.assertEqual(
            sum(isinstance(result, Payment) for result in results),
            1,
        )
        self.assertEqual(
            [
                str(result)
                for result in results
                if isinstance(result, OrderPaymentError)
            ],
            ["Payment already in progress"],
        )

    def test_retry_after_failed_payment(self):
        failed_payment = Payment.objects.create(
            order=self.order,
            status=Payment.Status.FAILED,
            amount=self.product.price,
        )

        payment = create_payment(self.order)

        self.assertNotEqual(payment.pk, failed_payment.pk)
        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertEqual(
            Payment.objects.filter(
                order=self.order,
                status__in=[
                    Payment.Status.CREATED,
                    Payment.Status.PENDING,
                ],
            ).count(),
            1,
        )
