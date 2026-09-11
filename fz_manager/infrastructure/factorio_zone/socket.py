import ssl

import certifi

from fz_manager.config import Settings
from fz_manager.infrastructure.factorio_zone.models import FzMessage
from fz_manager.utils.api_router.ws import WebSocketClient


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
        )
