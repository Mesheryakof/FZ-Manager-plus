"""Composition root: the only place that creates concrete runtime dependencies."""

import httpx

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.config import load_settings
from fz_manager_plus.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager_plus.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager_plus.tui.app import FzManagerApp


def create_app(argv: list[str] | None = None) -> FzManagerApp:
    settings, store = load_settings(argv)
    api = FactorioZoneAPI(settings, http=httpx.AsyncClient(timeout=30))
    session = FactorioZoneSession(api, FactorioZoneSocket(settings), settings)
    return FzManagerApp(settings, session, store)
