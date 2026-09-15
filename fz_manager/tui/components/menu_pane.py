from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ListItem, ListView, Static

STATIC_MENU_ITEMS = [
    "Manage mods",
    "Manage saves",
    "Exit",
]


class MenuPane(Vertical):
    DEFAULT_CSS = """
    MenuPane {
        width: 1fr;
        border: solid $secondary;
    }

    MenuPane > ListView {
        height: 1fr;
    }
    """

    def __init__(self, items: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_items = items

    def compose(self) -> ComposeResult:
        yield ListView(
            *[ListItem(Static(item), name=item) for item in self._initial_items],
            id="main-menu",
        )

    @property
    def list_view(self) -> ListView:
        return self.query_one("#main-menu", ListView)

    def sync_items(self, items: list[str]) -> None:
        menu = self.list_view
        current = [item.name for item in menu.children]
        if current == items:
            return
        menu.clear()
        for item in items:
            menu.append(ListItem(Static(item), name=item))
