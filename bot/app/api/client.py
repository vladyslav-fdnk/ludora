"""Reusable asynchronous client for the Ludora REST API."""

from typing import Any

import httpx

from app.auth.models import AuthResult, AuthTokens, BackendUser, TelegramIdentity
from app.auth.storage import TokenStorage

from .exceptions import (
    AuthenticationFailed,
    AuthenticationRequired,
    BackendTimeout,
    BackendUnavailable,
    InvalidResponse,
    ProductNotFound,
    UnexpectedAPIStatus,
)
from .schemas import Product, ProductPage


class BackendClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        *,
        internal_secret: str = "",
        token_storage: TokenStorage | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._internal_secret = internal_secret
        self._token_storage = token_storage
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout,
            transport=transport,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def authenticate_telegram(self, identity: TelegramIdentity) -> AuthResult:
        response = await self._send(
            "POST",
            "api/auth/telegram/",
            json=identity.as_payload(),
            headers={"X-Bot-Internal-Secret": self._internal_secret},
        )
        if response.status_code in {401, 403}:
            raise AuthenticationFailed
        self._raise_for_status(response)
        return AuthResult.from_mapping(self._json(response))

    async def get_profile(self, telegram_id: int) -> BackendUser:
        data = await self._authenticated_json("GET", "api/auth/me/", telegram_id)
        return BackendUser.from_mapping(data)

    async def get_products(self, page: int = 1) -> ProductPage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        data = await self._request_json("GET", "api/products/", params={"page": page})
        return ProductPage.from_mapping(data, page)

    async def get_product(self, product_id: int) -> Product:
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
            raise ValueError("product_id must be a positive integer")
        response = await self._send("GET", f"api/products/{product_id}/")
        if response.status_code == 404:
            raise ProductNotFound
        self._raise_for_status(response)
        return Product.from_mapping(self._json(response))

    async def close(self) -> None:
        await self._client.aclose()

    async def _authenticated_json(
        self,
        method: str,
        path: str,
        telegram_id: int,
    ) -> Any:
        if self._token_storage is None:
            raise AuthenticationRequired
        tokens = await self._token_storage.get(telegram_id)
        if tokens is None:
            raise AuthenticationRequired

        response = await self._send(
            method,
            path,
            headers={"Authorization": f"Bearer {tokens.access}"},
        )
        if response.status_code != 401:
            self._raise_for_status(response)
            return self._json(response)

        refreshed = await self._refresh(tokens.refresh, telegram_id)
        response = await self._send(
            method,
            path,
            headers={"Authorization": f"Bearer {refreshed.access}"},
        )
        if response.status_code == 401:
            await self._token_storage.delete(telegram_id)
            raise AuthenticationRequired
        self._raise_for_status(response)
        return self._json(response)

    async def _refresh(self, refresh_token: str, telegram_id: int) -> AuthTokens:
        response = await self._send(
            "POST",
            "api/auth/refresh/",
            json={"refresh": refresh_token},
        )
        if response.status_code in {400, 401}:
            if self._token_storage is not None:
                await self._token_storage.delete(telegram_id)
            raise AuthenticationRequired
        self._raise_for_status(response)
        data = self._json(response)
        access = data.get("access") if isinstance(data, dict) else None
        if not isinstance(access, str) or not access:
            raise InvalidResponse("Refresh response has no valid access token")
        tokens = AuthTokens(access=access, refresh=refresh_token)
        if self._token_storage is not None:
            await self._token_storage.set(telegram_id, tokens)
        return tokens

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, int] | None = None,
    ) -> Any:
        response = await self._send(method, path, params=params)
        self._raise_for_status(response)
        return self._json(response)

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise BackendTimeout from exc
        except httpx.RequestError as exc:
            raise BackendUnavailable from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if not 200 <= response.status_code < 300:
            raise UnexpectedAPIStatus(response.status_code)

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidResponse("Backend response is not valid JSON") from exc
