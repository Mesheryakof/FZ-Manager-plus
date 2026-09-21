import json
import ssl

import certifi
from pydantic import ValidationError

from fz_manager_plus.config import Settings
from fz_manager_plus.domain.messages import BlankMessage, FzMessage
from fz_manager_plus.utils.api_router.ws import WebSocketClient


def _to_blank_message(raw: str | bytes, error: ValidationError) -> BlankMessage:  # noqa: ARG001
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}
    data["type"] = str(data.get("type", "unknown"))
    return BlankMessage.model_validate(data)


class FactorioZoneSocket(WebSocketClient[FzMessage | BlankMessage]):
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
