from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, SelectionList, Static
from textual.widgets.selection_list import Selection


class MultiChoiceScreen(ModalScreen[list[str] | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    CSS = """
    MultiChoiceScreen {
        align: center middle;
    }

    #multi-choice-dialog {
        width: 70;
        height: auto;
        max-height: 24;
        border: solid $primary;
        padding: 1 2;
        background: $panel;
    }

    #multi-choice-dialog > SelectionList {
        height: auto;
        max-height: 16;
    }

    #multi-choice-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    #multi-choice-buttons > Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        preselected: list[str] = (),
    ) -> None:
        super().__init__()
        self._title = title
        self._options = options
        self._preselected = set(preselected)

    def compose(self) -> ComposeResult:
        with Vertical(id="multi-choice-dialog"):
            yield Static(self._title)
            yield SelectionList(
                *[
                    Selection(label, value, value in self._preselected)
                    for label, value in self._options
                ]
            )
            with Horizontal(id="multi-choice-buttons"):
                yield Button("Confirm", id="confirm", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "confirm":
            self.dismiss(self.query_one(SelectionList).selected)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
