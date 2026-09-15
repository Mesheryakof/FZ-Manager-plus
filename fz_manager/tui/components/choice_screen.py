from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static


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

    #choice-dialog > ListView {
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
            yield ListView(*[ListItem(Static(label), name=value) for label, value in self._options])

    def on_mount(self) -> None:
        if self._default is None:
            return
        list_view = self.query_one(ListView)
        for index, (_, value) in enumerate(self._options):
            if value == self._default:
                list_view.index = index
                break

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.dismiss(event.item.name)

    def action_cancel(self) -> None:
        self.dismiss(None)
