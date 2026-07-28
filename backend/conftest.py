"""Suite-wide safety guards for backend tests."""

import pytest
from stripe import _http_client


@pytest.fixture(autouse=True)
def fail_on_stripe_api_request(monkeypatch):
    """Fail immediately if any test reaches Stripe's HTTP transport."""

    def blocked_request(*args, **kwargs):
        pytest.fail("A real Stripe API request was attempted during a test")

    async def blocked_async_request(*args, **kwargs):
        pytest.fail("A real Stripe API request was attempted during a test")

    sync_methods = (
        "request_with_retries",
        "request_stream_with_retries",
    )
    async_methods = (
        "request_with_retries_async",
        "request_stream_with_retries_async",
    )
    for method_name in sync_methods:
        monkeypatch.setattr(_http_client.HTTPClient, method_name, blocked_request)
    for method_name in async_methods:
        monkeypatch.setattr(
            _http_client.HTTPClient,
            method_name,
            blocked_async_request,
        )
