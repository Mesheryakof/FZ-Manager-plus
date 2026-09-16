from __future__ import annotations

import asyncio
import contextlib
import traceback
from datetime import datetime, timezone
from enum import Enum

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ProgressBar

from fz_manager_plus.config import CRASH_LOG_PATH, Settings, get_settings
from fz_manager_plus.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager_plus.infrastructure.factorio_zone.session import FactorioZoneSession
from fz_manager_plus.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import (
    LogPane,
    MenuPane,
    ModsPane,
    SavesPane,
    SelectableList,
    StatusBar,
    TokenScreen,
)
from fz_manager_plus.tui.flows import ModFlows, SaveFlows, ServerFlows, SyncFlows
from fz_manager_plus.tui.progress import TransferProgress


class MenuAction(str, Enum):
    """Menu item labels, doubling as their SelectableList values -- `str`
    mixin so a member IS the label Textual actually stores/compares
    (SelectableList/ListItem work in plain strings; this doesn't change
    that, just gives the app side one typed name per action instead of
    the same string literal duplicated between the menu list and the
    dispatch below)."""

    START_SERVER = "Start server"
    STOP_SERVER = "Stop server"
    SYNC = "Sync mods with server"


STATIC_MENU_ITEMS = [
    MenuAction.SYNC,
]


class FzManagerApp(App):
    """Textual glue only: composing widgets, dispatching events, and the
    `@work` entry points Textual requires to live on the App itself (its
    worker decorator asserts `self` is a DOMNode). The actual business
    logic for each menu action lives in `tui.flows` -- plain classes that
    depend on this app only through the narrow `FlowHost` protocol, so
    they can be tested without booting the TUI.
    """

    TITLE = "Factorio Zone Manager PLUS"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-area {
        height: 1fr;
    }

    #sidebar {
        width: 1fr;
    }

    #menu-pane {
        height: auto;
    }

    #menu-pane > SelectableList {
        height: auto;
    }

    #bottom-bar {
        dock: bottom;
        height: auto;
    }

    #sync-progress {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        api = FactorioZoneAPI(self.settings)
        socket = FactorioZoneSocket(self.settings)
        self.session = FactorioZoneSession(api, socket)

        self.server_flows = ServerFlows(self)
        self.mod_flows = ModFlows(self)
        self.save_flows = SaveFlows(self)
        self.sync_flows = SyncFlows(self)

    def _handle_exception(self, error: Exception) -> None:

        wrapped = getattr(error, "error", None)
        if isinstance(wrapped, BaseException) and error.__cause__ is None:
            error.__cause__ = wrapped

        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG_PATH, "a") as fh:
            fh.write(f"\n--- {datetime.now(timezone.utc).isoformat()} ---\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=fh)
        super()._handle_exception(error)

    def _menu_items(self) -> list[MenuAction]:
        instance_item = (
            MenuAction.STOP_SERVER if self.session.launch_id is not None else MenuAction.START_SERVER
        )
        return [instance_item, *STATIC_MENU_ITEMS]

    @property
    def main_screen(self):
        return self.screen_stack[0]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-area"):
            yield LogPane(id="log-pane")
            with Vertical(id="sidebar"):
                yield MenuPane(self._menu_items(), id="menu-pane")
                yield ModsPane(self.session.mods, id="mods-pane")
                yield SavesPane(self.session.saves, id="saves-pane")
        with Vertical(id="bottom-bar"):
            yield StatusBar("", id="status-bar")
            progress_bar = ProgressBar(id="sync-progress", show_eta=False)
            progress_bar.display = False
            yield progress_bar
            yield Footer()

    def on_mount(self) -> None:
        self.theme = self.settings.theme
        self.session.add_logs_listener(self.push_log)
        self.set_interval(1, self._refresh_status_bar)
        self.set_interval(1, self._refresh_menu)
        self.set_interval(1, self._refresh_mods)
        self.set_interval(1, self._refresh_saves)
        self.main_screen.query_one(MenuPane).list_view.focus()
        if self.settings.user_token:
            self._start_connecting()
        else:
            self.push_screen(
                TokenScreen(default=self.settings.user_token or ""), self._on_token_submitted
            )

    def _on_token_submitted(self, token: str) -> None:
        self.settings.user_token = token or None
        self._start_connecting()

    def _start_connecting(self) -> None:
        self.main_screen.query_one(LogPane).log_view.write(Text("Connecting to factorio.zone...", style="dim"))
        self.connect_client()

    def _refresh_status_bar(self) -> None:
        self.main_screen.query_one(StatusBar).update_status(
            self.session.launch_id, self.session.server_status, self.session.server_address
        )

    async def _refresh_menu(self) -> None:
        await self.main_screen.query_one(MenuPane).sync_items(self._menu_items())

    async def _refresh_mods(self) -> None:
        await self.main_screen.query_one(ModsPane).sync_mods(self.session.mods)

    async def _refresh_saves(self) -> None:
        await self.main_screen.query_one(SavesPane).sync_saves(self.session.saves)

    @work(exclusive=True, group="ws-connect")
    async def connect_client(self) -> None:
        try:
            await self.session.connect()
            await self.session.run()
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[connection error]", str(ex)))

    def push_log(self, *log: str) -> None:
        if not log:
            return
        text = " ".join(log)
        self.main_screen.query_one(LogPane).log_view.write(Text.from_ansi(text))

    def start_transfer_progress(self, total: float) -> TransferProgress:
        bar = self.main_screen.query_one("#sync-progress", ProgressBar)
        return TransferProgress(bar, total)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        if self.session.launch_id is None:
            self.push_log(Term.error("COMMAND:", "No running server to attach to."))
            return
        self.push_log(Term.info("Sent command:", text))
        self.send_command(text)

    @work(group="send-command")
    async def send_command(self, command: str) -> None:
        try:
            await self.session.send_command(command)
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[command]", str(ex)))

    def on_selectable_list_picked(self, event: SelectableList.Picked) -> None:
        if event.selectable_list is not self.main_screen.query_one(MenuPane).list_view:
            return
        try:
            action = MenuAction(event.value)
        except ValueError:
            self.main_screen.query_one(LogPane).log_view.write(
                Text(f"[menu] '{event.value}' is not implemented yet.", style="italic dim")
            )
            return

        match action:
            case MenuAction.START_SERVER:
                self.start_server_flow()
            case MenuAction.STOP_SERVER:
                self.stop_server_flow()
            case MenuAction.SYNC:
                self.sync_flow()

    def on_mods_pane_toggled(self, event: ModsPane.Toggled) -> None:
        self.toggle_mod(event.mod_id, event.enabled)

    @work(group="toggle-mod")
    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        await self.mod_flows.toggle(mod_id, enabled)

    def on_mods_pane_delete_requested(self, event: ModsPane.DeleteRequested) -> None:
        self.delete_mod_flow(event.mod_id)

    @work(exclusive=False, group="delete-mod")
    async def delete_mod_flow(self, mod_id: int) -> None:
        await self.mod_flows.delete(mod_id)

    def on_saves_pane_download_requested(self, event: SavesPane.DownloadRequested) -> None:
        self.download_save_slot_flow(event.slot)

    @work(exclusive=False, group="download-save")
    async def download_save_slot_flow(self, slot: str) -> None:
        await self.save_flows.download(slot)

    def on_saves_pane_delete_requested(self, event: SavesPane.DeleteRequested) -> None:
        self.delete_save_slot_flow(event.slot)

    @work(exclusive=False, group="delete-save")
    async def delete_save_slot_flow(self, slot: str) -> None:
        await self.save_flows.delete(slot)

    @work(exclusive=True, group="start-server")
    async def start_server_flow(self) -> None:
        await self.server_flows.start()

    @work(exclusive=True, group="stop-server")
    async def stop_server_flow(self) -> None:
        await self.server_flows.stop()

    @work(exclusive=True, group="sync")
    async def sync_flow(self) -> None:
        await self.sync_flows.run()

    async def action_quit(self) -> None:
        self.session.remove_logs_listener(self.push_log)
        if self.session.user_token:
            self.settings.user_token = self.session.user_token
        self.workers.cancel_group(self, "ws-connect")
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.session.socket.close(), timeout=2)
        self.exit()


def main() -> None:
    FzManagerApp(settings=get_settings()).run()


if __name__ == "__main__":
    main()
