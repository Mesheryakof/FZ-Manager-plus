from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button

from fz_manager_plus.tui.components.selectable_list import SelectableList


class SavesPane(Vertical):
    DEFAULT_CSS = """
    SavesPane {
        height: 1fr;
        border: solid $secondary;
    }

    SavesPane > SelectableList {
        height: 1fr;
    }

    SavesPane > #save-actions {
        height: 3;
    }
    """

    BINDINGS = [
        ("delete,backspace", "delete_highlighted", "Delete save"),
        ("d", "download_highlighted", "Download save"),
        ("u", "upload_highlighted", "Upload save"),
    ]

    class DownloadRequested(Message):
        def __init__(self, saves_pane: SavesPane, slot: str) -> None:
            super().__init__()
            self.saves_pane = saves_pane
            self.slot = slot

    class UploadRequested(Message):
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
        self._hovered_slot: str | None = None

    @staticmethod
    def _build_options(saves: dict[str, str]) -> list[tuple[str, str]]:
        return [(f"{slot}: {description}", slot) for slot, description in sorted(saves.items())]

    def on_mount(self) -> None:
        self.border_title = "Saves"

    def compose(self) -> ComposeResult:
        yield SelectableList(self._build_options(self._saves))
        with Horizontal(id="save-actions"):
            yield Button("Download", id="save-download-button", disabled=True)
            yield Button("Upload", id="save-upload-button", disabled=True)
            yield Button("Delete", id="save-delete-button", variant="error", disabled=True)

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

    def on_selectable_list_hovered(self, event: SelectableList.Hovered) -> None:
        event.stop()
        self._hovered_slot = event.value
        for button_id in ("save-download-button", "save-upload-button", "save-delete-button"):
            self.query_one(f"#{button_id}", Button).disabled = False

    def _highlighted_slot(self) -> str | None:
        # ListView's cursor attribute is `index`, not `highlighted`
        # (that's SelectionList/OptionList's name for the same concept --
        # see ModsPane.action_delete_highlighted for the other one).
        index = self.list_view.index
        if index is None:
            return None
        return self.list_view.children[index].name

    def action_delete_highlighted(self) -> None:
        if (slot := self._highlighted_slot()) is not None:
            self.post_message(self.DeleteRequested(self, slot))

    def action_download_highlighted(self) -> None:
        if (slot := self._highlighted_slot()) is not None:
            self.post_message(self.DownloadRequested(self, slot))

    def action_upload_highlighted(self) -> None:
        if (slot := self._highlighted_slot()) is not None:
            self.post_message(self.UploadRequested(self, slot))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._hovered_slot is None:
            return
        if event.button.id == "save-download-button":
            event.stop()
            self.post_message(self.DownloadRequested(self, self._hovered_slot))
        elif event.button.id == "save-upload-button":
            event.stop()
            self.post_message(self.UploadRequested(self, self._hovered_slot))
        elif event.button.id == "save-delete-button":
            event.stop()
            self.post_message(self.DeleteRequested(self, self._hovered_slot))
