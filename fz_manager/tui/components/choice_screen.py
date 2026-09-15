from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from fz_manager.tui.components.selectable_list import SelectableList


class ChoiceScreen(ModalScreen[str | None]):
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

    #choice-dialog > SelectableList {
        height: auto;
        max-height: 14;
    }
    """

    def __init__(
        self, title: str, options: list[tuple[str, str]], default: str | None = None
    ) -> None:
        super().__init__()
        self._title = title
        self._options = options
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-dialog"):
            yield Static(self._title)
            yield SelectableList(self._options)

    def on_mount(self) -> None:
        if self._default is None:
            return
        index = self.query_one(SelectableList).index_of(self._default)
        if index is not None:
            self.query_one(SelectableList).index = index

    def on_selectable_list_picked(self, event: SelectableList.Picked) -> None:
        event.stop()
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
