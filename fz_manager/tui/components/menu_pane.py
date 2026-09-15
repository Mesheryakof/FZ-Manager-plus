from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical

from fz_manager.tui.components.selectable_list import SelectableList


class MenuPane(Vertical):
    DEFAULT_CSS = """
    MenuPane {
        width: 1fr;
        border: solid $secondary;
    }

    MenuPane > SelectableList {
        height: 1fr;
    }
    """

    def __init__(self, items: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_items = items

    def compose(self) -> ComposeResult:
        yield SelectableList([(item, item) for item in self._initial_items])

    @property
    def list_view(self) -> SelectableList:
        return self.query_one(SelectableList)

    def sync_items(self, items: list[str]) -> None:
        self.list_view.sync_options([(item, item) for item in items])
