from __future__ import annotations

from textual.message import Message
from textual.widgets import ListItem, ListView, Static


class SelectableList(ListView):
    # Not named `Selected`: ListView's own Enter-key handling does
    # `self.post_message(self.Selected(self, item))` internally, resolved
    # by attribute lookup -- a class named `Selected` here would shadow
    # that and get constructed by ListView's code with the wrong args.
    class Picked(Message):
        def __init__(self, selectable_list: SelectableList, value: str) -> None:
            super().__init__()
            self.selectable_list = selectable_list
            self.value = value

    def __init__(self, options: list[tuple[str, str]] | None = None, **kwargs) -> None:
        self._options = list(options or [])
        super().__init__(*self._build_items(self._options), **kwargs)

    @staticmethod
    def _build_items(options: list[tuple[str, str]]) -> list[ListItem]:
        return [ListItem(Static(label), name=value) for label, value in options]

    def sync_options(self, options: list[tuple[str, str]]) -> None:
        if options == self._options:
            return
        self._options = list(options)
        self.clear()
        for item in self._build_items(options):
            self.append(item)

    def index_of(self, value: str) -> int | None:
        for index, (_, option_value) in enumerate(self._options):
            if option_value == value:
                return index
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.post_message(self.Picked(self, event.item.name))
