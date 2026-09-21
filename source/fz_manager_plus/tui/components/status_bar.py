from __future__ import annotations

import webbrowser

from textual.widgets import Static

# https://forums.factorio.com/viewtopic.php?t=129411 - "steam://connect/" doesn't
# work because Factorio's server doesn't implement the Steam Game Server API;
# "steam://run/<appid>//<launch args>/" does, by reusing --mp-connect.
FACTORIO_STEAM_APP_ID = 427520


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
            parts.append(f"Server: [@click=open_in_steam({server_address!r})]{server_address}[/]")
        self.update(" | ".join(parts))

    def action_open_in_steam(self, server_address: str) -> None:
        url = f"steam://run/{FACTORIO_STEAM_APP_ID}//--mp-connect%20{server_address}/"
        webbrowser.open(url)
