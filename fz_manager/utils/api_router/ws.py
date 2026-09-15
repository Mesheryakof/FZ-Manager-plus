import ssl
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError
from websockets import client as ws_client
from websockets.client import WebSocketClientProtocol

TMessage = TypeVar("TMessage")
THandler = Callable[[Any, Any], Awaitable[None]]

_UNSET = object()


class WebSocketClient(Generic[TMessage]):
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls._handlers: dict[type, THandler] = {}
        cls._default_handler: THandler | None = None

    def __init__(
        self,
        url: str,
        message_model,
        *,
        ssl_context: ssl.SSLContext | None = None,
        ping_interval: float = 30,
        ping_timeout: float = 10,
        on_decode_error: Callable[[bytes, ValidationError], TMessage] | None = None,
    ):
        self._url = url
        self._message_adapter = TypeAdapter(message_model)
        self._ssl_context = ssl_context
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._on_decode_error = on_decode_error
        self._socket: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._socket = await ws_client.connect(
            self._url,
            ssl=self._ssl_context,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        )

    @property
    def socket(self) -> WebSocketClientProtocol:
        if not self._socket:
            raise RuntimeError('Socket is not initialized! Please use before .connect()')
        return self._socket

    async def messages(self) -> AsyncIterator[TMessage]:
        async for raw in self.socket:
            try:
                yield self._message_adapter.validate_json(raw)
            except ValidationError as e:
                if self._on_decode_error is None:
                    raise
                yield self._on_decode_error(raw, e)

    async def send(self, message: BaseModel) -> None:
        await self.socket.send(message.model_dump_json(by_alias=True))

    async def close(self) -> None:
        if self._socket is not None:
            await self._socket.close()

    @classmethod
    def on(cls, message_type: type | None = None):
        def decorator(fn: THandler) -> THandler:
            if message_type is None:
                cls._default_handler = fn
            else:
                cls._handlers[message_type] = fn
            return fn

        return decorator

    async def dispatch(self, session: Any, message: Any) -> None:
        handler = type(self)._handlers.get(type(message), type(self)._default_handler)
        if handler is not None:
            await handler(session, message)

    async def listen(self, session: Any) -> None:
        async for message in self.messages():
            await self.dispatch(session, message)
