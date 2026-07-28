"""Django settings used by the backend pytest suite."""

from config.settings import *  # noqa: F403

# Tests must not inherit payment configuration from the host environment.
PAYMENT_PROVIDER = "local"
STRIPE_SECRET_KEY = "sk_test_dummy"
STRIPE_WEBHOOK_SECRET = "whsec_test_dummy"
STRIPE_CURRENCY = "usd"
STRIPE_SUCCESS_URL = "http://localhost/payments/success"
STRIPE_CANCEL_URL = "http://localhost/payments/cancel"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
