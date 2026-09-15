"""Generic single-choice picker modal, reused for region/version/slot
selection in the "Start server" flow."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


class ChoiceScreen(ModalScreen[str | None]):
    """Generic single-choice picker: a titled list of options, dismisses
    with the selected value, or `None` if cancelled (Escape).

    Reused for region/version/slot selection in the "Start server" flow --
    ported from the old `Main.choose_region`/`choose_factorio_version`/
    `choose_slot` (questionary `SelectMenu` screens), just as one shared
    Textual modal instead of three near-identical ones.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    CSS = """
    ChoiceScreen {
        align: center middle;
    }

    #choice-dialog {
        width: 60;
        height: auto;
        max-height: 20;
        border: solid $primary;
        padding: 1 2;
        background: $panel;
    }

    #choice-dialog > ListView {
        height: auto;
        max-height: 14;
    }
    """

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self._title = title
        self._options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-dialog"):
            yield Static(self._title)
            yield ListView(*[ListItem(Static(label), name=value) for label, value in self._options])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.dismiss(event.item.name)

    def action_cancel(self) -> None:
        self.dismiss(None)
