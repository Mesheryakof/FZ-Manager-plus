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

    def update_status(
        self, launch_id: int | None, server_status: str, server_address: str | None
    ) -> None:
        """Ported from the old `ui/titlebar.py`'s `Server {status} at:
        {address}` line, folded into this single-line status bar instead of
        its own titlebar row. Takes plain values rather than a `session`
        object -- keeps this widget presentational, not session-aware."""
        parts = [
            "Trial: N/A",
            f"Launch ID: {launch_id if launch_id is not None else '-'}",
            f"Status: {server_status}",
        ]
        if server_address:
            parts.append(f"Server: {server_address}")
        self.update(" | ".join(parts))
