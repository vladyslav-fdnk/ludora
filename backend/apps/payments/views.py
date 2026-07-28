from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.webhooks import (
    InvalidStripeWebhook,
    parse_stripe_webhook,
    process_stripe_webhook,
)


class StripeWebhookAPIView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    http_method_names = ("post", "options")

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="The Stripe event was acknowledged."),
            400: OpenApiResponse(description="The Stripe webhook is invalid."),
        },
        description="Verify and acknowledge a Stripe webhook event.",
        auth=[],
    )
    def post(self, request):
        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not isinstance(secret, str) or not secret.strip():
            raise ImproperlyConfigured(
                "STRIPE_WEBHOOK_SECRET must be configured for Stripe webhooks"
            )

        try:
            result = parse_stripe_webhook(
                payload=request.body,
                signature=request.headers.get("Stripe-Signature", ""),
                secret=secret.strip(),
            )
            process_stripe_webhook(result)
        except InvalidStripeWebhook:
            return Response(
                {"error": "Invalid Stripe webhook"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"received": True},
            status=status.HTTP_200_OK,
        )
