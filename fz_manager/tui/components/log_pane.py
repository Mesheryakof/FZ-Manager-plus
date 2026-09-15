from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog


class LogPane(Vertical):
    DEFAULT_CSS = """
    LogPane {
        width: 3fr;
        border: solid $primary;
    }

    LogPane > #log-view {
        height: 1fr;
    }

    LogPane > #command-input {
        height: 3;
        border: none;
        border-top: solid $primary;
    }
    """

    def on_mount(self) -> None:
        self.border_title = "Logs"

    def compose(self) -> ComposeResult:
        log_view = RichLog(id="log-view", wrap=False, highlight=False, markup=False)
        log_view.can_focus = False
        yield log_view
        yield Input(placeholder="Type a message and press Enter...", id="command-input")

    @property
    def log_view(self) -> RichLog:
        return self.query_one("#log-view", RichLog)

    @property
    def command_input(self) -> Input:
        return self.query_one("#command-input", Input)
