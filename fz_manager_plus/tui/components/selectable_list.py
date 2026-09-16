from __future__ import annotations

from functools import partial

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import ListItem, ListView, Static


class SelectableList(ListView):
    class Picked(Message):
        def __init__(self, selectable_list: SelectableList, value: str) -> None:
            super().__init__()
            self.selectable_list = selectable_list
            self.value = value

    class Hovered(Message):
        """Posted when the mouse moves over a different item."""

        def __init__(self, selectable_list: SelectableList, value: str) -> None:
            super().__init__()
            self.selectable_list = selectable_list
            self.value = value

    def __init__(self, options: list[tuple[str, str]] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._options = list(options or [])

    @staticmethod
    def _build_items(options: list[tuple[str, str]]) -> list[ListItem]:
        return [ListItem(Static(label), name=value) for label, value in options]

    def compose(self) -> ComposeResult:
        yield from self._build_items(self._options)

    def on_mount(self) -> None:
        self._watch_item_hover()

    def _watch_item_hover(self) -> None:
        # ListItem stops Enter/Leave itself (for its own "-hovered" CSS
        # class), so they never bubble up here. `mouse_hover` only updates on
        # the exact widget under the mouse (Widget._on_enter checks
        # `event.node is self`), which is each item's inner Static, not the
        # ListItem -- so that's what's watched, per item.
        for item in self.children:
            self.watch(
                item.query_one(Static),
                "mouse_hover",
                partial(self._on_item_hover, item),
                init=False,
            )

    def _on_item_hover(self, item: ListItem, is_hovering: bool) -> None:
        if is_hovering:
            self.post_message(self.Hovered(self, item.name))

    async def sync_options(self, options: list[tuple[str, str]]) -> None:
        if options == self._options:
            return
        index = self.index
        value = (
            self.children[index].name if index is not None and index < len(self.children) else None
        )
        focused, scroll_y = self.has_focus, self.scroll_y
        self._options = list(options)
        await self.recompose()
        self._watch_item_hover()
        self.index = self.index_of(value) if value is not None else None
        if self.index is None and options:
            self.index = 0
        self.call_after_refresh(self.scroll_to, y=scroll_y, animate=False, force=True)
        if focused:
            self.focus(scroll_visible=False)

    def index_of(self, value: str) -> int | None:
        for index, (_, option_value) in enumerate(self._options):
            if option_value == value:
                return index
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.post_message(self.Picked(self, event.item.name))
