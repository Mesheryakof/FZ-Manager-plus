"""Reusable Textual components for the FZ-Manager dashboard TUI.

Mirrors a typical frontend `components/` split: `fz_manager.tui.app` owns
application wiring (session, layout, event routing) and stays thin, while
each self-contained UI piece -- a modal screen or a dashboard pane -- lives
here in its own module with its own `compose()`/CSS.
"""

from fz_manager.tui.components.choice_screen import ChoiceScreen
from fz_manager.tui.components.confirm_screen import ConfirmScreen
from fz_manager.tui.components.log_pane import LogPane
from fz_manager.tui.components.menu_pane import STATIC_MENU_ITEMS, MenuPane
from fz_manager.tui.components.status_bar import StatusBar
from fz_manager.tui.components.token_screen import TokenScreen

__all__ = [
    "ChoiceScreen",
    "ConfirmScreen",
    "LogPane",
    "MenuPane",
    "STATIC_MENU_ITEMS",
    "StatusBar",
    "TokenScreen",
]
