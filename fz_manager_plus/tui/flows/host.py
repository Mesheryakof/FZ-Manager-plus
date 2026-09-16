from __future__ import annotations

from typing import Any, Protocol

from rich.text import Text

from fz_manager_plus.config import Settings
from fz_manager_plus.infrastructure.factorio_zone.session import FactorioZoneSession


class FlowHost(Protocol):
    """Narrow view of `FzManagerApp` that flow controllers depend on --
    just enough to run business logic and talk to the user, without
    pulling in the rest of Textual's `App` surface (widgets, workers,
    screen stack, ...). Lets flow classes be plain, host-agnostic objects
    that a test can satisfy with a stub instead of booting the TUI.
    """

    settings: Settings
    session: FactorioZoneSession

    def push_log(self, message: str | Text) -> None: ...

    async def push_screen_wait(self, screen: Any) -> Any: ...
