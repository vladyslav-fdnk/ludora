from django.urls import path

from apps.payments.views import StripeWebhookAPIView

app_name = "payments"

urlpatterns = [
    path(
        "stripe/webhook/",
        StripeWebhookAPIView.as_view(),
        name="stripe-webhook",
    ),
]
