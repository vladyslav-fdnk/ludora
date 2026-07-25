"""Reusable asynchronous client for the Ludora REST API."""

from typing import Any

import httpx

from .exceptions import (
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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            timeout=timeout,
            transport=transport,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def get_products(self, page: int = 1) -> ProductPage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        data = await self._get_json("api/products/", params={"page": page})
        return ProductPage.from_mapping(data, page)

    async def get_product(self, product_id: int) -> Product:
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
            raise ValueError("product_id must be a positive integer")
        data = await self._get_json(f"api/products/{product_id}/", product_detail=True)
        return Product.from_mapping(data)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, int] | None = None,
        product_detail: bool = False,
    ) -> Any:
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise BackendTimeout from exc
        except httpx.RequestError as exc:
            raise BackendUnavailable from exc
        if product_detail and response.status_code == 404:
            raise ProductNotFound
        if not 200 <= response.status_code < 300:
            raise UnexpectedAPIStatus(response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidResponse("Backend response is not valid JSON") from exc
