from __future__ import annotations

from collections.abc import Awaitable, Callable

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, ProgressBar, Static

from fz_manager_plus.domain.state import TransferEvent, TransferProgress, TransferResult
from fz_manager_plus.domain.state import UploadItem as UploadItem

type UploadRunner = Callable[[Callable[[TransferEvent], None]], Awaitable[list[str]]]


class ModsUploadScreen(ModalScreen[list[str] | None]):
    """Lists items about to be uploaded, each with its own progress bar.
    Cancelling before upload starts dismisses with `None`; once started,
    each row fills independently (up to `batch_size` concurrently) and the
    dialog can only be closed after every row finishes -- dismissing then
    with the list of labels that failed (empty if all succeeded).
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    CSS = """
    ModsUploadScreen {
        align: center middle;
    }

    #upload-dialog {
        width: 76;
        height: auto;
        max-height: 26;
        border: solid $primary;
        padding: 1 2;
        background: $panel;
    }

    #upload-list {
        height: auto;
        max-height: 14;
        margin-top: 1;
    }

    .upload-row {
        height: 1;
        margin-bottom: 1;
    }

    .upload-row > .upload-label {
        width: 28;
        content-align: left middle;
    }

    .upload-row > ProgressBar {
        width: 1fr;
    }

    #upload-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    #upload-buttons > Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, items: list[UploadItem], run_uploads: UploadRunner) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._run_batch = run_uploads
        self._labels: list[Static] = []
        self._bars: list[ProgressBar] = []
        self._failed: list[str] = []
        self._started = False
        self._finished = False

    def compose(self) -> ComposeResult:
        with Vertical(id="upload-dialog"):
            yield Static(self._title)
            with VerticalScroll(id="upload-list"):
                for item in self._items:
                    with Horizontal(classes="upload-row"):
                        yield Static(
                            Text(item.label, no_wrap=True, overflow="ellipsis"),
                            classes="upload-label",
                        )
                        yield ProgressBar(total=item.size or None, show_eta=False)
            with Horizontal(id="upload-buttons"):
                yield Button("Upload", id="confirm", variant="success")
                yield Button("Cancel", id="cancel", variant="error")
                close_button = Button("Close", id="close", variant="primary")
                close_button.display = False
                yield close_button

    def on_mount(self) -> None:
        self._labels = list(self.query(".upload-label"))
        self._bars = list(self.query(ProgressBar))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "cancel" and not self._started:
            self.dismiss(None)
        elif event.button.id == "close" and self._finished:
            self.dismiss(self._failed)
        elif event.button.id == "confirm" and not self._started:
            self._started = True
            self.query_one("#confirm", Button).display = False
            self.query_one("#cancel", Button).display = False
            self._run_uploads()

    def action_cancel(self) -> None:
        if not self._started:
            self.dismiss(None)
        elif self._finished:
            self.dismiss(self._failed)
        # else: upload in progress -- ignore, must wait for it to finish

    @work(exclusive=True)
    async def _run_uploads(self) -> None:
        try:
            self._failed = await self._run_batch(self._on_transfer)
        except Exception as error:
            self._failed = [item.label for item in self._items]
            for index in range(len(self._items)):
                self._on_transfer(TransferResult(index, str(error) or type(error).__name__))
        self._finished = True
        self.query_one("#close", Button).display = True

    def _on_transfer(self, event: TransferEvent) -> None:
        item, bar, label = (
            self._items[event.index],
            self._bars[event.index],
            self._labels[event.index],
        )
        if isinstance(event, TransferProgress):
            bar.update(progress=event.bytes_done)
        elif event.error is None:
            bar.update(progress=item.size)
            label.update(Text(f"{item.label} ✓", no_wrap=True, overflow="ellipsis"))
        else:
            label.update(
                Text(
                    f"{item.label} ✗ {event.error}",
                    style="bold red",
                    no_wrap=True,
                    overflow="ellipsis",
                )
            )
