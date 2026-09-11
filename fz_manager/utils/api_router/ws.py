"""Generic async WebSocket client built on top of `websockets` + pydantic.

Incoming frames are decoded into a pydantic type (which can be a
discriminated union via `Annotated[Union[...], Field(discriminator=...)]`)
through `TypeAdapter`, and outgoing pydantic models are sent as JSON.
"""

import ssl
from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from pydantic import BaseModel, TypeAdapter
from websockets import client as ws_client
from websockets.client import WebSocketClientProtocol

TMessage = TypeVar("TMessage")


class WebSocketClient(Generic[TMessage]):
    """Generic async WS client that decodes incoming frames into
    `message_model` and can send pydantic models as JSON."""

    def __init__(
        self,
        url: str,
        message_model,
        *,
        ssl_context: ssl.SSLContext | None = None,
        ping_interval: float = 30,
        ping_timeout: float = 10,
    ):
        self._url = url
        self._message_adapter = TypeAdapter(message_model)
        self._ssl_context = ssl_context
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._socket: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._socket = await ws_client.connect(
            self._url,
            ssl=self._ssl_context,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        )

    async def messages(self) -> AsyncIterator[TMessage]:
        async for raw in self._socket:
            yield self._message_adapter.validate_json(raw)

    async def send(self, message: BaseModel) -> None:
        await self._socket.send(message.model_dump_json(by_alias=True))

    async def close(self) -> None:
        if self._socket is not None:
            await self._socket.close()
