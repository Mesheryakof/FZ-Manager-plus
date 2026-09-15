import json
import ssl

import certifi
from pydantic import ValidationError

from fz_manager.config import Settings
from fz_manager.infrastructure.factorio_zone.models import BlankMessage, FzMessage
from fz_manager.utils.api_router.ws import WebSocketClient


def _to_blank_message(raw: bytes, error: ValidationError) -> BlankMessage:  # noqa: ARG001
    """`on_decode_error` hook: turns a frame that failed to validate against
    `FzMessage` into a `BlankMessage` instead of letting the error kill the
    message loop -- see `BlankMessage`'s docstring."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}
    data["type"] = str(data.get("type", "unknown"))
    return BlankMessage.model_validate(data)


class FactorioZoneSocket(WebSocketClient):
    def __init__(self, settings: Settings):
        self.settings = settings
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        super().__init__(
            f"wss://{self.settings.factorio_zone_endpoint}/ws",
            FzMessage,
            ssl_context=ssl_context,
            ping_interval=self.settings.ws_ping_interval,
            ping_timeout=self.settings.ws_ping_timeout,
            on_decode_error=_to_blank_message,
        )
