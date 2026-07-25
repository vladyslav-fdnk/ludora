from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.api.client import BackendClient
from app.api.exceptions import AuthenticationFailed, AuthenticationRequired, InvalidResponse
from app.auth import (
    AuthResult,
    AuthTokens,
    BackendUser,
    InMemoryTokenStorage,
    TelegramIdentity,
)
from app.auth.service import TelegramAuthService


def telegram_user(**overrides):
    values = {
        "id": 123,
        "username": "vlad",
        "first_name": "Vlad",
        "last_name": None,
        "language_code": "ru",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def profile_payload():
    return {
        "id": 7,
        "email": "telegram-123@bot.ludora.invalid",
        "first_name": "Vlad",
        "last_name": "",
        "telegram_username": "vlad",
        "telegram_language_code": "ru",
        "date_joined": "2026-07-25T10:00:00Z",
    }


def auth_payload():
    return {"access": "access-1", "refresh": "refresh-1", "user": profile_payload()}


async def test_in_memory_token_storage_round_trip_and_delete():
    storage = InMemoryTokenStorage()
    tokens = AuthTokens("access", "refresh")
    assert await storage.get(123) is None
    await storage.set(123, tokens)
    assert await storage.get(123) == tokens
    await storage.delete(123)
    assert await storage.get(123) is None


async def test_authentication_service_synchronizes_payload_and_stores_tokens():
    seen = {}

    async def handler(request):
        seen["json"] = request.content
        assert request.headers["X-Bot-Internal-Secret"] == "secret"
        return httpx.Response(200, json=auth_payload())

    storage = InMemoryTokenStorage()
    client = BackendClient(
        "https://backend.test",
        1,
        internal_secret="secret",
        token_storage=storage,
        transport=httpx.MockTransport(handler),
    )
    result = await TelegramAuthService(client, storage).synchronize(telegram_user())
    assert result.user.first_name == "Vlad"
    assert await storage.get(123) == AuthTokens("access-1", "refresh-1")
    assert b'"telegram_id":123' in seen["json"]
    await client.close()


async def test_authenticated_request_uses_access_token():
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer access"
        return httpx.Response(200, json=profile_payload())

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("access", "refresh"))
    client = BackendClient(
        "https://backend.test", 1, token_storage=storage, transport=httpx.MockTransport(handler)
    )
    assert (await client.get_profile(123)).email.endswith(".invalid")
    await client.close()


async def test_401_refreshes_and_retries_original_request_once():
    requests = []

    async def handler(request):
        requests.append((request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/api/auth/refresh/":
            return httpx.Response(200, json={"access": "new-access"})
        if request.headers["Authorization"] == "Bearer old-access":
            return httpx.Response(401)
        return httpx.Response(200, json=profile_payload())

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("old-access", "refresh"))
    client = BackendClient(
        "https://backend.test", 1, token_storage=storage, transport=httpx.MockTransport(handler)
    )
    await client.get_profile(123)
    assert len(requests) == 3
    assert await storage.get(123) == AuthTokens("new-access", "refresh")
    await client.close()


@pytest.mark.parametrize("refresh_response", [httpx.Response(401), httpx.Response(400)])
async def test_failed_refresh_clears_tokens(refresh_response):
    async def handler(request):
        if request.url.path == "/api/auth/refresh/":
            return refresh_response
        return httpx.Response(401)

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("old", "bad-refresh"))
    client = BackendClient(
        "https://backend.test", 1, token_storage=storage, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AuthenticationRequired):
        await client.get_profile(123)
    assert await storage.get(123) is None
    await client.close()


async def test_second_401_does_not_refresh_again():
    paths = []

    async def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/api/auth/refresh/":
            return httpx.Response(200, json={"access": "new"})
        return httpx.Response(401)

    storage = InMemoryTokenStorage()
    await storage.set(123, AuthTokens("old", "refresh"))
    client = BackendClient(
        "https://backend.test", 1, token_storage=storage, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AuthenticationRequired):
        await client.get_profile(123)
    assert paths.count("/api/auth/refresh/") == 1
    assert paths.count("/api/auth/me/") == 2
    await client.close()


async def test_rejected_sync_and_malformed_sync_are_classified():
    for response, exception in [
        (httpx.Response(401), AuthenticationFailed),
        (httpx.Response(200, json={"access": "only"}), InvalidResponse),
    ]:
        client = BackendClient(
            "https://backend.test",
            1,
            transport=httpx.MockTransport(lambda request, response=response: response),
        )
        with pytest.raises(exception):
            await client.authenticate_telegram(TelegramIdentity(123))
        await client.close()


def test_backend_user_fixture_is_timezone_aware():
    user = BackendUser(
        "email",
        "first",
        "last",
        "username",
        "ru",
        datetime(2026, 7, 25, tzinfo=UTC),
    )
    result = AuthResult(AuthTokens("access", "refresh"), user)
    assert result.user.date_joined.tzinfo is UTC
