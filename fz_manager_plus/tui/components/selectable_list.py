from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import ListItem, ListView, Static


class SelectableList(ListView):
    class Picked(Message):
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
