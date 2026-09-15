"""Bottom status bar -- trial/launch-id summary."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Just a `Static` with a typed `update_status()` instead of a raw
    `.update(f"...")` call scattered around the App."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def update_status(self, launch_id: int | None) -> None:
        self.update(f"Trial: N/A | Launch ID: {launch_id if launch_id is not None else '-'}")
