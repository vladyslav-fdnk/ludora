import httpx
import pytest

from app.api.client import BackendClient
from app.api.exceptions import (
    BackendTimeout,
    BackendUnavailable,
    InvalidResponse,
    ProductNotFound,
    UnexpectedAPIStatus,
)


def payload(**overrides):
    value = {
        "id": 7,
        "title": "Portal",
        "slug": "portal",
        "price": "29.99",
        "platform": "Steam",
        "product_type": "GAME",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize("page", [0, -1])
async def test_rejects_invalid_page(page):
    client = BackendClient("https://backend.test", 1)
    with pytest.raises(ValueError):
        await client.get_products(page)
    await client.close()


async def test_parses_page_and_sends_page_parameter():
    async def handler(request):
        assert request.url.path == "/api/products/"
        assert request.url.params["page"] == "2"
        return httpx.Response(
            200,
            json={
                "count": 11,
                "next": None,
                "previous": "https://backend.test/api/products/?page=1",
                "results": [payload()],
            },
        )

    client = BackendClient("https://backend.test/", 1, transport=httpx.MockTransport(handler))
    page = await client.get_products(2)
    assert page.page == 2
    assert page.has_previous and not page.has_next
    assert page.products[0].price.as_tuple().exponent == -2
    await client.close()
    assert client.is_closed


async def test_parses_detail_and_optional_fields():
    async def handler(request):
        assert request.url.path == "/api/products/7/"
        return httpx.Response(
            200,
            json=payload(description=None, categories=["Puzzle"], is_active=True),
        )

    client = BackendClient("https://backend.test", 1, transport=httpx.MockTransport(handler))
    product = await client.get_product(7)
    assert product.description is None
    assert product.categories == ("Puzzle",)
    await client.close()


@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (httpx.Response(404), ProductNotFound),
        (httpx.Response(503), UnexpectedAPIStatus),
        (httpx.Response(200, text="{"), InvalidResponse),
        (
            httpx.Response(
                200,
                json={"count": 1, "next": None, "previous": None, "results": [{}]},
            ),
            InvalidResponse,
        ),
    ],
)
async def test_maps_response_failures(response, exception):
    client = BackendClient(
        "https://backend.test",
        1,
        transport=httpx.MockTransport(lambda request: response),
    )
    with pytest.raises(exception):
        if response.status_code == 404:
            await client.get_product(7)
        else:
            await client.get_products()
    await client.close()


@pytest.mark.parametrize(
    ("failure", "exception"),
    [
        (httpx.ReadTimeout("slow"), BackendTimeout),
        (httpx.ConnectError("offline"), BackendUnavailable),
    ],
)
async def test_maps_transport_failures(failure, exception):
    def handler(request):
        raise failure

    client = BackendClient(
        "https://backend.test",
        1,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(exception):
        await client.get_products()
    await client.close()
