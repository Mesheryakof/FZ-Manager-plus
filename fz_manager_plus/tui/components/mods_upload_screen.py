from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, ProgressBar, Static

from fz_manager_plus.utils.concurrency import run_batched


@dataclass
class UploadItem:
    """One row in `ModsUploadScreen`: `label` is shown to the user, `size`
    sizes the row's progress bar (0 for unknown), and `upload` performs the
    actual transfer given a `bytes_done` progress callback."""

    label: str
    size: int
    upload: Callable[[Callable[[int], None]], Awaitable[None]]


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

    def __init__(self, title: str, items: list[UploadItem], batch_size: int) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._batch_size = batch_size
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
        if event.button.id == "cancel":
            self.dismiss(None)
        elif event.button.id == "close":
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
        async def run_one(index: int) -> None:
            item = self._items[index]
            bar = self._bars[index]
            label = self._labels[index]
            try:
                await item.upload(lambda bytes_done: bar.update(progress=bytes_done))
                bar.update(progress=item.size or bar.progress)
                label.update(Text(f"{item.label} ✓", no_wrap=True, overflow="ellipsis"))
            except Exception as ex:  # noqa: BLE001
                self._failed.append(item.label)
                label.update(
                    Text(
                        f"{item.label} ✗ {ex}",
                        style="bold red",
                        no_wrap=True,
                        overflow="ellipsis",
                    )
                )

        jobs = [(lambda i=i: run_one(i)) for i in range(len(self._items))]
        await run_batched(jobs, self._batch_size)

        self._finished = True
        self.query_one("#close", Button).display = True
