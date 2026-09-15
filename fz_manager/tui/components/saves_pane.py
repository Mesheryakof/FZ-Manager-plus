from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message

from fz_manager.tui.components.selectable_list import SelectableList


class SavesPane(Vertical):
    DEFAULT_CSS = """
    SavesPane {
        height: 1fr;
        border: solid $secondary;
    }

    SavesPane > SelectableList {
        height: 1fr;
    }
    """

    BINDINGS = [("delete,backspace", "delete_highlighted", "Delete save")]

    class DownloadRequested(Message):
        def __init__(self, saves_pane: SavesPane, slot: str) -> None:
            super().__init__()
            self.saves_pane = saves_pane
            self.slot = slot

    class DeleteRequested(Message):
        def __init__(self, saves_pane: SavesPane, slot: str) -> None:
            super().__init__()
            self.saves_pane = saves_pane
            self.slot = slot

    def __init__(self, saves: dict[str, str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._saves = dict(saves or {})

    @staticmethod
    def _build_options(saves: dict[str, str]) -> list[tuple[str, str]]:
        return [(f"{slot}: {description}", slot) for slot, description in sorted(saves.items())]

    def on_mount(self) -> None:
        self.border_title = "Saves"

    def compose(self) -> ComposeResult:
        yield SelectableList(self._build_options(self._saves))

    @property
    def list_view(self) -> SelectableList:
        return self.query_one(SelectableList)

    async def sync_saves(self, saves: dict[str, str]) -> None:
        if saves == self._saves:
            return
        self._saves = dict(saves)
        await self.list_view.sync_options(self._build_options(saves))

    def on_selectable_list_picked(self, event: SelectableList.Picked) -> None:
        event.stop()
        self.post_message(self.DownloadRequested(self, event.value))

    def action_delete_highlighted(self) -> None:
        # ListView's cursor attribute is `index`, not `highlighted`
        # (that's SelectionList/OptionList's name for the same concept --
        # see ModsPane.action_delete_highlighted for the other one).
        index = self.list_view.index
        if index is None:
            return
        item = self.list_view.children[index]
        self.post_message(self.DeleteRequested(self, item.name))
