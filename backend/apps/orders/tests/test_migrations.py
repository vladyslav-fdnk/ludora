from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class DirectOrderBackfillMigrationTests(TransactionTestCase):
    migrate_from = ("orders", "0006_order_source_order_total_price_alter_order_product_and_more")
    migrate_to = ("orders", "0007_backfill_direct_order_items")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        self._create_legacy_orders(old_apps)

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _create_legacy_orders(self, apps):
        Platform = apps.get_model("games", "Platform")
        Product = apps.get_model("games", "Product")
        Order = apps.get_model("orders", "Order")
        OrderItem = apps.get_model("orders", "OrderItem")
        Payment = apps.get_model("orders", "Payment")

        platform = Platform.objects.create(name="Steam", slug="migration-steam")
        product = Product.objects.create(
            title="Historical Game",
            slug="historical-game",
            product_type="GAME",
            platform=platform,
            price=Decimal("99.99"),
        )
        self.paid_order_id = Order.objects.create(
            product=product,
            email="paid@example.com",
            price_paid=Decimal("49.99"),
            source="DIRECT",
        ).pk
        Payment.objects.create(
            order_id=self.paid_order_id,
            status="PAID",
            amount=Decimal("59.99"),
        )
        self.payment_order_id = Order.objects.create(
            product=product,
            email="payment@example.com",
            source="DIRECT",
        ).pk
        Payment.objects.create(
            order_id=self.payment_order_id,
            status="PAID",
            amount=Decimal("39.99"),
        )
        self.catalogue_order_id = Order.objects.create(
            product=product,
            email="catalogue@example.com",
            source="DIRECT",
        ).pk
        self.missing_product_order_id = Order.objects.create(
            product=None,
            email="missing@example.com",
            price_paid=Decimal("29.99"),
            source="DIRECT",
        ).pk
        self.authoritative_order_id = Order.objects.create(
            product=product,
            email="authoritative@example.com",
            total_price=Decimal("19.99"),
            price_paid=Decimal("29.99"),
            source="DIRECT",
        ).pk
        Payment.objects.create(
            order_id=self.authoritative_order_id,
            status="PAID",
            amount=Decimal("39.99"),
        )

        second_product = Product.objects.create(
            title="Historical DLC",
            slug="historical-dlc",
            product_type="DLC",
            platform=platform,
            price=Decimal("20.00"),
        )
        self.items_order_id = Order.objects.create(
            product=product,
            email="items@example.com",
            source="DIRECT",
        ).pk
        OrderItem.objects.create(
            order_id=self.items_order_id,
            product_id=product.pk,
            product_title="Old Game Title",
            quantity=2,
            unit_price=Decimal("10.00"),
        )
        OrderItem.objects.create(
            order_id=self.items_order_id,
            product_id=second_product.pk,
            product_title="Old DLC Title",
            quantity=3,
            unit_price=Decimal("5.00"),
        )

        self.unresolved_paid_order_id = Order.objects.create(
            product=product,
            email="unresolved-paid@example.com",
            status="PAID",
            source="DIRECT",
        ).pk

        blank_product = Product.objects.create(
            title="",
            slug="blank-title",
            product_type="GAME",
            platform=platform,
            price=Decimal("9.99"),
        )
        self.blank_title_order_id = Order.objects.create(
            product=blank_product,
            email="blank@example.com",
            source="DIRECT",
        ).pk

    def test_backfill_uses_reliable_amount_precedence_and_snapshots(self):
        Order = self.apps.get_model("orders", "Order")
        OrderItem = self.apps.get_model("orders", "OrderItem")

        expected = {
            self.paid_order_id: Decimal("49.99"),
            self.payment_order_id: Decimal("39.99"),
            self.catalogue_order_id: Decimal("99.99"),
        }
        for order_id, amount in expected.items():
            order = Order.objects.get(pk=order_id)
            item = OrderItem.objects.get(order_id=order_id)
            self.assertEqual(order.total_price, amount)
            self.assertEqual(item.unit_price, amount)
            self.assertEqual(item.quantity, 1)
            self.assertEqual(item.product_title, "Historical Game")

        missing_product = Order.objects.get(pk=self.missing_product_order_id)
        self.assertEqual(missing_product.total_price, Decimal("29.99"))
        self.assertFalse(
            OrderItem.objects.filter(order_id=self.missing_product_order_id).exists()
        )

        authoritative = Order.objects.get(pk=self.authoritative_order_id)
        self.assertEqual(authoritative.total_price, Decimal("19.99"))
        self.assertEqual(
            OrderItem.objects.get(order_id=self.authoritative_order_id).unit_price,
            Decimal("19.99"),
        )

        items_order = Order.objects.get(pk=self.items_order_id)
        self.assertEqual(items_order.total_price, Decimal("35.00"))
        self.assertEqual(
            OrderItem.objects.filter(order_id=self.items_order_id).count(),
            2,
        )

        unresolved_paid = Order.objects.get(pk=self.unresolved_paid_order_id)
        self.assertIsNone(unresolved_paid.total_price)
        self.assertFalse(
            OrderItem.objects.filter(order_id=self.unresolved_paid_order_id).exists()
        )

        blank_title = Order.objects.get(pk=self.blank_title_order_id)
        self.assertEqual(blank_title.total_price, Decimal("9.99"))
        self.assertFalse(
            OrderItem.objects.filter(order_id=self.blank_title_order_id).exists()
        )


class LicenseAssignmentBackfillMigrationTests(TransactionTestCase):
    migrate_from = ("orders", "0008_order_financial_constraints")
    migrate_to = ("orders", "0009_licenseassignment")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        self._create_orders(old_apps)

        self.executor = MigrationExecutor(connection)
        with self.assertLogs(
            "apps.orders.migrations.0009_licenseassignment",
            level="WARNING",
        ) as migration_logs:
            self.executor.migrate([self.migrate_to])
        self.migration_logs = migration_logs.output
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _create_orders(self, apps):
        LicenseKey = apps.get_model("games", "LicenseKey")
        Order = apps.get_model("orders", "Order")
        OrderItem = apps.get_model("orders", "OrderItem")
        Platform = apps.get_model("games", "Platform")
        Product = apps.get_model("games", "Product")

        platform = Platform.objects.create(name="Steam", slug="assignment-steam")
        product = Product.objects.create(
            title="Assigned Game",
            slug="assigned-game",
            product_type="GAME",
            platform=platform,
            price=Decimal("49.99"),
        )
        assigned_key = LicenseKey.objects.create(
            product=product,
            value="ASSIGNED-KEY",
            status="SOLD",
        )
        paid_order = Order.objects.create(
            product=product,
            email="paid@example.com",
            source="DIRECT",
            status="PAID",
            license_key=assigned_key,
        )
        self.paid_item_id = OrderItem.objects.create(
            order=paid_order,
            product=product,
            product_title=product.title,
            quantity=1,
            unit_price=product.price,
        ).pk
        self.assigned_key_id = assigned_key.pk

        malformed_key = LicenseKey.objects.create(
            product=product,
            value="MALFORMED-KEY",
            status="SOLD",
        )
        self.malformed_order_id = Order.objects.create(
            product=product,
            email="malformed@example.com",
            source="DIRECT",
            status="PAID",
            license_key=malformed_key,
        ).pk
        self.malformed_key_id = malformed_key.pk

        unassigned_key = LicenseKey.objects.create(
            product=product,
            value="UNASSIGNED-KEY",
            status="AVAILABLE",
        )
        unpaid_order = Order.objects.create(
            product=product,
            email="unpaid@example.com",
            source="DIRECT",
            status="CREATED",
            license_key=unassigned_key,
        )
        OrderItem.objects.create(
            order=unpaid_order,
            product=product,
            product_title=product.title,
            quantity=1,
            unit_price=product.price,
        )

    def test_backfills_only_paid_direct_order_license_keys(self):
        LicenseAssignment = self.apps.get_model("orders", "LicenseAssignment")

        assignment = LicenseAssignment.objects.get()
        self.assertEqual(assignment.order_item_id, self.paid_item_id)
        self.assertEqual(assignment.license_key_id, self.assigned_key_id)

    def test_skips_and_reports_paid_direct_order_without_order_item(self):
        LicenseAssignment = self.apps.get_model("orders", "LicenseAssignment")

        self.assertFalse(
            LicenseAssignment.objects.filter(
                license_key_id=self.malformed_key_id
            ).exists()
        )
        self.assertTrue(
            any(
                str(self.malformed_order_id) in message
                and "without exactly one OrderItem" in message
                for message in self.migration_logs
            )
        )

    def test_license_key_can_only_be_assigned_once(self):
        LicenseAssignment = self.apps.get_model("orders", "LicenseAssignment")

        with self.assertRaises(IntegrityError), transaction.atomic():
            LicenseAssignment.objects.create(
                order_item_id=self.paid_item_id,
                license_key_id=self.assigned_key_id,
            )
