import asyncio

import httpx
import pytest
from pydantic import BaseModel

from fz_manager.utils.api_router.http import ApiError, ApiRouterHttp, DecodeError


class Widget(BaseModel):
    name: str
    count: int


def make_toy_client(transport: httpx.MockTransport):
    http = httpx.AsyncClient(base_url="https://example.test", transport=transport)
    router = ApiRouterHttp(http)

    class ToyApiClient:
        @router.endpoint(response_model=Widget)
        def get_widget(self) -> httpx.Request:
            return router.build_request(method="GET", path="/widget")

    return ToyApiClient()


def test_endpoint_parses_successful_response_into_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "gizmo", "count": 3})

    client = make_toy_client(httpx.MockTransport(handler))

    widget = asyncio.run(client.get_widget())

    assert widget == Widget(name="gizmo", count=3)


def test_endpoint_raises_api_error_on_non_2xx_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = make_toy_client(httpx.MockTransport(handler))

    with pytest.raises(ApiError) as exc_info:
        asyncio.run(client.get_widget())

    assert exc_info.value.status_code == 404
    assert exc_info.value.body == "not found"


def test_endpoint_raises_decode_error_on_malformed_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "gizmo"})  # missing required `count`

    client = make_toy_client(httpx.MockTransport(handler))

    with pytest.raises(DecodeError):
        asyncio.run(client.get_widget())
