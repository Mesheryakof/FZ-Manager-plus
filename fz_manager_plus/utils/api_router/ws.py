import ssl
from collections.abc import AsyncIterator, Callable

from pydantic import TypeAdapter, ValidationError
from websockets import client as ws_client
from websockets.exceptions import InvalidStatusCode, WebSocketException

from fz_manager_plus.domain.errors import AuthenticationError, DisconnectedError


class WebSocketClient[TMessage]:
    """One connection; reconnection and message handling belong to the session."""

    def __init__(
        self,
        url: str,
        message_model,
        *,
        ssl_context: ssl.SSLContext | None = None,
        ping_interval: float = 30,
        ping_timeout: float = 10,
        on_decode_error: Callable[[str | bytes, ValidationError], TMessage] | None = None,
    ):
        self._url = url
        self._message_adapter = TypeAdapter(message_model)
        self._ssl_context = ssl_context
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._on_decode_error = on_decode_error
        self._socket = None

    async def connect(self) -> None:
        try:
            self._socket = await ws_client.connect(
                self._url,
                ssl=self._ssl_context,
                ping_interval=self._ping_interval,
                ping_timeout=self._ping_timeout,
                close_timeout=2,
            )
        except InvalidStatusCode as error:
            if error.status_code in (401, 403):
                raise AuthenticationError(
                    "Authentication failed. Enter your token again."
                ) from error
            raise DisconnectedError(str(error)) from error
        except (OSError, TimeoutError, WebSocketException) as error:
            raise DisconnectedError(str(error)) from error

    async def messages(self) -> AsyncIterator[TMessage]:
        if self._socket is None:
            raise DisconnectedError("Socket is not connected")
        try:
            async for raw in self._socket:
                try:
                    yield self._message_adapter.validate_json(raw)
                except ValidationError as error:
                    if self._on_decode_error is None:
                        raise
                    yield self._on_decode_error(raw, error)
        except (OSError, WebSocketException) as error:
            raise DisconnectedError(str(error)) from error

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()
