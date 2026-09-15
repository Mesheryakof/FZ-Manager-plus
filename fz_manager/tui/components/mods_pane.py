from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection


class ModsPane(Vertical):
    DEFAULT_CSS = """
    ModsPane {
        height: 1fr;
        border: solid $secondary;
    }

    ModsPane > SelectionList {
        height: 1fr;
    }
    """

    BINDINGS = [("delete,backspace", "delete_highlighted", "Delete mod")]

    class Toggled(Message):
        def __init__(self, mods_pane: ModsPane, mod_id: int, enabled: bool) -> None:
            super().__init__()
            self.mods_pane = mods_pane
            self.mod_id = mod_id
            self.enabled = enabled

    class DeleteRequested(Message):
        def __init__(self, mods_pane: ModsPane, mod_id: int) -> None:
            super().__init__()
            self.mods_pane = mods_pane
            self.mod_id = mod_id

    def __init__(self, mods: list[dict] = (), **kwargs) -> None:
        super().__init__(**kwargs)
        self._mods = list(mods)

    @staticmethod
    def _build_selections(mods: list[dict]) -> list[Selection]:
        return [Selection(mod["text"], mod["id"], mod["enabled"]) for mod in mods]

    def compose(self) -> ComposeResult:
        yield SelectionList(*self._build_selections(self._mods))

    @property
    def selection_list(self) -> SelectionList:
        return self.query_one(SelectionList)

    def sync_mods(self, mods: list[dict]) -> None:
        if mods == self._mods:
            return
        self._mods = list(mods)
        selection_list = self.selection_list
        selection_list.clear_options()
        selection_list.add_options(self._build_selections(mods))

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        event.stop()
        mod_id = event.selection.value
        enabled = mod_id in self.selection_list.selected
        self.post_message(self.Toggled(self, mod_id, enabled))

    def action_delete_highlighted(self) -> None:
        highlighted = self.selection_list.highlighted
        if highlighted is None:
            return
        selection = self.selection_list.get_option_at_index(highlighted)
        self.post_message(self.DeleteRequested(self, selection.value))
