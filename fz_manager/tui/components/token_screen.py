"""Modal asking for the factorio.zone user token before connecting."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class TokenScreen(ModalScreen[str]):
    """Modal asking for the factorio.zone user token before connecting.

    Dismisses with the entered token (possibly empty -- factorio.zone issues
    a fresh one on first visit if none is given, same as the old
    `Main.choose_token()` flow).
    """

    CSS = """
    TokenScreen {
        align: center middle;
    }

    #token-dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        padding: 1 2;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="token-dialog"):
            yield Static("Enter your factorio.zone user token (leave empty for a new one):")
            yield Input(placeholder="user token", password=True, id="token-input")

    def on_mount(self) -> None:
        self.query_one("#token-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value.strip())
