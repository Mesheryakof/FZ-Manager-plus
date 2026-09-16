from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
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
        parts = [
            f"Launch ID: {launch_id if launch_id is not None else '-'}",
            f"Status: {server_status}",
        ]
        if server_address:
            parts.append(f"Server: {server_address}")
        self.update(" | ".join(parts))
