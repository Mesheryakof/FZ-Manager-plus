"""Static action menu pane -- lists server/mod/save actions."""

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
    """Wraps the `#main-menu` `ListView`.

    Takes the *initial* item list in the constructor; `FzManagerApp` polls
    session state and calls `sync_items(items)` to keep it in sync (e.g.
    swapping "Start server" for "Stop server" once a launch id shows up).
    `ListView.Selected` fired here bubbles up to the App unchanged, so
    `on_list_view_selected` still lives on `FzManagerApp`.

    Named `sync_items`, not `refresh`, because `refresh` is already
    `Widget.refresh()` (repaint/layout) -- shadowing it with an incompatible
    signature breaks Textual's own internals (e.g. `await_mount`).
    """

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
