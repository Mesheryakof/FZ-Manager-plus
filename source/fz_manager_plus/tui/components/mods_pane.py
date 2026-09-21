from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection

from fz_manager_plus.domain.state import Mod


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

    BINDINGS = [
        ("delete,backspace", "delete_highlighted", "Delete mod"),
        ("t", "toggle_highlighted", "Toggle mod"),
    ]

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

    def __init__(self, mods: list[Mod] | tuple[Mod, ...] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mods = list(mods or [])

    @staticmethod
    def _build_selections(mods: list[Mod]) -> list[Selection]:
        # no_wrap+ellipsis: SelectionList.render_line() maps a rendered row
        # to an option via `scroll_y + y`, assuming exactly one row per
        # option -- a mod name long enough to wrap onto a second row breaks
        # that math and crashes with OptionDoesNotExist (a Textual bug, not
        # a sync-timing issue -- confirmed by reproducing it with a single
        # long-named option and no mutation involved at all).
        return [
            Selection(Text(mod.text, no_wrap=True, overflow="ellipsis"), mod.id, mod.enabled)
            for mod in mods
        ]

    def on_mount(self) -> None:
        self.border_title = "Mods"

    def compose(self) -> ComposeResult:
        yield SelectionList(*self._build_selections(self._mods))

    @property
    def selection_list(self) -> SelectionList:
        return self.query_one(SelectionList)

    async def sync_mods(self, mods: list[Mod] | tuple[Mod, ...], *, force: bool = False) -> None:
        if list(mods) == self._mods and not force:
            return
        old = self.selection_list
        focused, scroll_y, highlighted = old.has_focus, old.scroll_y, old.highlighted
        value = old.get_option_at_index(highlighted).value if highlighted is not None else None
        self._mods = list(mods)
        # recompose(): Textual's own atomic "remove children, call compose()
        # again" primitive. clear_options()+add_options() (previously used
        # here) each mutate SelectionList's internal option/line bookkeeping
        # separately and can leave it briefly inconsistent -- recompose()
        # rebuilds the whole SelectionList from scratch instead of patching
        # it in place, so there's no partial state to observe.
        await self.recompose()
        current = self.selection_list
        current.highlighted = next(
            (i for i, mod in enumerate(self._mods) if mod.id == value), 0 if self._mods else None
        )
        current.call_after_refresh(current.scroll_to, y=scroll_y, animate=False, force=True)
        if focused:
            current.focus(scroll_visible=False)

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

    def action_toggle_highlighted(self) -> None:
        highlighted = self.selection_list.highlighted
        if highlighted is None:
            return
        mod_id = self.selection_list.get_option_at_index(highlighted).value
        enabled = mod_id not in self.selection_list.selected
        self.post_message(self.Toggled(self, mod_id, enabled))
