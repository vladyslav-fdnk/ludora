from contextlib import redirect_stderr
from io import StringIO

from rest_framework import status
from rest_framework.test import APITestCase


class OrderSchemaTests(APITestCase):
    def setUp(self):
        stderr = StringIO()
        with redirect_stderr(stderr):
            self.response = self.client.get(
                "/api/schema/",
                HTTP_ACCEPT="application/json",
            )
        self.schema_stderr = stderr.getvalue()

    def _resolve_schema(self, schema):
        reference = schema.get("$ref")
        if reference:
            component_name = reference.rsplit("/", maxsplit=1)[-1]
            return self.response.data["components"]["schemas"][component_name]
        return schema

    def _json_schema(self, content):
        return self._resolve_schema(content["application/json"]["schema"])

    def test_schema_is_generated_without_affected_view_warnings(self):
        self.assertEqual(self.response.status_code, status.HTTP_200_OK)

        for view_name in (
            "OrderPayAPIView",
            "MyOrdersAPIView",
            "PaymentCreateAPIView",
        ):
            self.assertNotIn(view_name, self.schema_stderr)

    def test_affected_order_endpoints_are_present(self):
        paths = self.response.data["paths"]

        self.assertIn("/api/orders/{id}/pay/", paths)
        self.assertIn("/api/orders/my/", paths)
        self.assertIn("/api/orders/payments/", paths)

    def test_order_pay_schema_matches_api_payloads(self):
        operation = self.response.data["paths"]["/api/orders/{id}/pay/"]["post"]

        self.assertNotIn("requestBody", operation)
        success_schema = self._json_schema(
            operation["responses"]["200"]["content"],
        )
        self.assertEqual(
            set(success_schema["properties"]),
            {
                "message",
                "order_number",
                "license_key",
                "price_paid",
                "paid_at",
            },
        )

        for response_status in ("400", "404"):
            error_schema = self._json_schema(
                operation["responses"][response_status]["content"],
            )
            self.assertEqual(set(error_schema["properties"]), {"error"})

    def test_my_orders_schema_exposes_normalized_items_and_totals(self):
        operation = self.response.data["paths"]["/api/orders/my/"]["get"]
        page_schema = self._json_schema(operation["responses"]["200"]["content"])
        item_schema = self._json_schema(
            {"application/json": {"schema": page_schema["properties"]["results"]["items"]}}
        )

        self.assertEqual(
            set(item_schema["properties"]),
            {
                "id",
                "order_number",
                "product",
                "status",
                "source",
                "total_price",
                "price_paid",
                "created_at",
                "paid_at",
                "items",
            },
        )

    def test_payment_create_schema_matches_api_payloads(self):
        operation = self.response.data["paths"]["/api/orders/payments/"]["post"]
        request_schema = self._json_schema(
            operation["requestBody"]["content"],
        )
        response_schema = self._json_schema(
            operation["responses"]["201"]["content"],
        )

        self.assertEqual(set(request_schema["properties"]), {"order"})
        self.assertEqual(request_schema["required"], ["order"])
        self.assertEqual(
            set(response_schema["properties"]),
            {"id", "order", "status", "amount", "created_at"},
        )

        for response_status in ("400", "404"):
            error_schema = self._json_schema(
                operation["responses"][response_status]["content"],
            )
            self.assertEqual(set(error_schema["properties"]), {"error"})
