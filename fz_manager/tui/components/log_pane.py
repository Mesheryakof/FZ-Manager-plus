"""Log stream + command input pane -- the dashboard's main content area."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog


class LogPane(Vertical):
    """Live log stream on top of a command input box.

    Purely presentational -- `FzManagerApp` owns the actual log/session
    state and reaches in via `query_one(LogPane).log_view`/`.command_input`.
    `Input.Submitted` events fired here bubble up to the App unchanged, so
    `on_input_submitted` still lives on `FzManagerApp`.
    """

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
