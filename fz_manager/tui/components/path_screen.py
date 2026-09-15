from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class PathScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    CSS = """
    PathScreen {
        align: center middle;
    }

    #path-dialog {
        width: 80;
        height: auto;
        border: solid $primary;
        padding: 1 2;
        background: $panel;
    }

    #path-error {
        color: $error;
        height: auto;
    }
    """

    def __init__(
        self,
        title: str,
        default: str = "",
        validator: Callable[[str], bool] = lambda value: True,
        error_message: str = "Invalid value.",
    ) -> None:
        super().__init__()
        self._title = title
        self._default = default
        self._validator = validator
        self._error_message = error_message

    def compose(self) -> ComposeResult:
        with Vertical(id="path-dialog"):
            yield Static(self._title)
            yield Input(value=self._default, placeholder="path", id="path-input")
            yield Static("", id="path-error")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        value = event.value.strip()
        if not self._validator(value):
            self.query_one("#path-error", Static).update(self._error_message)
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)
