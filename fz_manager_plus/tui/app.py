from __future__ import annotations

import asyncio
import contextlib
import traceback
from datetime import UTC, datetime
from enum import StrEnum

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.config import Settings, SettingsStore
from fz_manager_plus.domain.state import (
    AuthenticationRequired,
    ConnectionStatus,
    LogEvent,
    SessionEvent,
    StateChanged,
    TokenReceived,
)
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import (
    LogPane,
    MenuPane,
    ModsPane,
    SavesPane,
    SelectableList,
    StatusBar,
    TokenScreen,
    VersionLabel,
)
from fz_manager_plus.tui.flows import ModFlows, SaveFlows, ServerFlows, SyncFlows


class MenuAction(StrEnum):
    """Menu item labels, doubling as their SelectableList values -- `str`
    mixin so a member IS the label Textual actually stores/compares
    (SelectableList/ListItem work in plain strings; this doesn't change
    that, just gives the app side one typed name per action instead of
    the same string literal duplicated between the menu list and the
    dispatch below)."""

    START_SERVER = "Start server"
    STOP_SERVER = "Stop server"
    SYNC = "Sync mods with server"
    DELETE_ALL_MODS = "Delete all mods"


STATIC_MENU_ITEMS = [
    MenuAction.SYNC,
    MenuAction.DELETE_ALL_MODS,
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

    #saves-pane {
        height: 1fr;
    }

    #mods-pane {
        height: 4fr;
    }

    #bottom-bar {
        dock: bottom;
        height: 2;
    }

    #status-row {
        height: 1;
    }

    #status-bar {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    class SessionUpdated(Message):
        def __init__(self, event: SessionEvent):
            super().__init__()
            self.event = event

    def __init__(
        self, settings: Settings, session: FactorioZoneSession, store: SettingsStore
    ) -> None:
        super().__init__()
        self.settings = settings
        self.session, self.store = session, store
        self._dialog_lock = asyncio.Lock()
        self._resources_closed = False
        self._refresh_pending = False
        self._restore_mod_selection = False

        self.server_flows = ServerFlows(self)
        self.mod_flows = ModFlows(self)
        self.save_flows = SaveFlows(self)
        self.sync_flows = SyncFlows(self)

    def _handle_exception(self, error: Exception) -> None:

        wrapped = getattr(error, "error", None)
        if isinstance(wrapped, BaseException) and error.__cause__ is None:
            error.__cause__ = wrapped

        with contextlib.suppress(OSError):
            self.store.crash_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.store.crash_log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"\n--- {datetime.now(UTC).isoformat()} ---\n")
                traceback.print_exception(type(error), error, error.__traceback__, file=fh)
        super()._handle_exception(error)

    def _menu_items(self) -> list[MenuAction]:
        instance_item = (
            MenuAction.STOP_SERVER
            if self.session.launch_id is not None
            else MenuAction.START_SERVER
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
                yield SavesPane(self.session.saves, id="saves-pane")
                yield ModsPane(self.session.mods, id="mods-pane")
        with Vertical(id="bottom-bar"):
            with Horizontal(id="status-row"):
                yield StatusBar("", id="status-bar")
                yield VersionLabel()
            yield Footer()

    def on_mount(self) -> None:
        self.theme = self.settings.theme
        self.session.subscribe(self._session_event)
        self.call_next(self._refresh_state)
        self.main_screen.query_one(MenuPane).list_view.focus()
        if self.settings.user_token:
            self._start_connecting()
        else:
            self.push_screen(
                TokenScreen(default=self.settings.user_token or ""), self._on_token_submitted
            )

    def _on_token_submitted(self, token: str | None) -> None:
        if token is None:
            return
        self.settings.user_token = token or None
        self.session.api.user_token = self.settings.user_token
        self._start_connecting()

    def _start_connecting(self) -> None:
        self.main_screen.query_one(LogPane).log_view.write(
            Text("Connecting to factorio.zone...", style="dim")
        )
        self.connect_client()

    def _refresh_status_bar(self) -> None:
        self.main_screen.query_one(StatusBar).update_status(
            self.session.launch_id,
            f"{self.session.server_status} / {self.session.state.connection}",
            self.session.server_address,
        )

    async def save_settings(self) -> None:
        try:
            await self.store.save(self.settings)
        except OSError as error:
            self.push_log(Term.error("[settings] Could not save preferences:", str(error)))

    async def _session_event(self, event: SessionEvent) -> None:
        if isinstance(event, TokenReceived):
            self.settings.user_token = event.token
            await self.save_settings()
        self.post_message(self.SessionUpdated(event))

    def on_fz_manager_app_session_updated(self, message: SessionUpdated) -> None:
        event = message.event
        if isinstance(event, LogEvent):
            self.push_log(Term.event(event))
        elif isinstance(event, StateChanged) and not self._refresh_pending:
            self._refresh_pending = True
            self.call_next(self._refresh_state)
        elif isinstance(event, AuthenticationRequired):
            self.push_log(Term.error(event.message))
            self.push_screen(
                TokenScreen(default=self.settings.user_token or ""), self._on_token_submitted
            )

    async def _refresh_state(self) -> None:
        self._refresh_pending = False
        state = self.session.state
        available = state.connection in (ConnectionStatus.SYNCING, ConnectionStatus.CONNECTED)
        self.main_screen.query_one(MenuPane).disabled = not (available and "auth" in state.ready)
        self.main_screen.query_one(ModsPane).disabled = not (
            available and {"auth", "mods"} <= state.ready
        )
        self.main_screen.query_one(SavesPane).disabled = not (
            available and {"auth", "saves"} <= state.ready
        )
        self.main_screen.query_one(LogPane).command_input.disabled = not (
            available and {"auth", "server"} <= state.ready
        )
        self._refresh_status_bar()
        await self._refresh_menu()
        await self._refresh_mods()
        await self._refresh_saves()

    async def _refresh_menu(self) -> None:
        pane = self.main_screen.query_one(MenuPane)
        await pane.sync_items(self._menu_items())
        requirements = {
            MenuAction.START_SERVER: {"auth", "server", "regions", "versions", "saves"},
            MenuAction.STOP_SERVER: {"auth", "server"},
            MenuAction.SYNC: {"auth", "mods"},
            MenuAction.DELETE_ALL_MODS: {"auth", "mods"},
        }
        for item in pane.list_view.children:
            item.disabled = not requirements[MenuAction(item.name)] <= self.session.state.ready

    async def _refresh_mods(self) -> None:
        restore, self._restore_mod_selection = self._restore_mod_selection, False
        await self.main_screen.query_one(ModsPane).sync_mods(self.session.mods, force=restore)

    async def _refresh_saves(self) -> None:
        await self.main_screen.query_one(SavesPane).sync_saves(self.session.saves)

    @work(exclusive=True, group="ws-connect")
    async def connect_client(self) -> None:
        try:
            await self.session.run()
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[connection error]", str(ex)))

    def push_log(self, message: str | Text) -> None:
        if not message:
            return
        self.main_screen.query_one(LogPane).log_view.write(message)

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
        self.send_command(text)

    @work(group="send-command")
    async def send_command(self, command: str) -> None:
        try:
            await self.session.send_command(command)
            self.push_log(Term.info("Sent command:", command))
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
            case MenuAction.DELETE_ALL_MODS:
                self.delete_all_mods_flow()

    def on_mods_pane_toggled(self, event: ModsPane.Toggled) -> None:
        self.toggle_mod(event.mod_id, event.enabled)

    @work(group="toggle-mod")
    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        await self._run_flow(
            "manage mods", lambda: self.mod_flows.toggle(mod_id, enabled), dialog=False
        )
        self._restore_mod_selection = True
        self.post_message(self.SessionUpdated(StateChanged(self.session.state.revision)))

    def on_mods_pane_delete_requested(self, event: ModsPane.DeleteRequested) -> None:
        self.delete_mod_flow(event.mod_id)

    @work(exclusive=False, group="delete-mod")
    async def delete_mod_flow(self, mod_id: int) -> None:
        await self._run_flow("delete mod", lambda: self.mod_flows.delete(mod_id))

    @work(group="delete-all-mods")
    async def delete_all_mods_flow(self) -> None:
        await self._run_flow("delete mods", self.mod_flows.delete_all)

    def on_saves_pane_download_requested(self, event: SavesPane.DownloadRequested) -> None:
        self.download_save_slot_flow(event.slot)

    @work(exclusive=False, group="download-save")
    async def download_save_slot_flow(self, slot: str) -> None:
        await self._run_flow("download save", lambda: self.save_flows.download(slot))

    def on_saves_pane_delete_requested(self, event: SavesPane.DeleteRequested) -> None:
        self.delete_save_slot_flow(event.slot)

    @work(exclusive=False, group="delete-save")
    async def delete_save_slot_flow(self, slot: str) -> None:
        await self._run_flow("delete save", lambda: self.save_flows.delete(slot))

    @work(group="start-server")
    async def start_server_flow(self) -> None:
        await self._run_flow("start server", self.server_flows.start)

    @work(group="stop-server")
    async def stop_server_flow(self) -> None:
        await self._run_flow("stop server", self.server_flows.stop)

    @work(group="sync")
    async def sync_flow(self) -> None:
        await self._run_flow("sync", self.sync_flows.run)

    async def _run_flow(self, label, operation, *, dialog: bool = True) -> None:
        if dialog and self._dialog_lock.locked():
            self.push_log(Term.warn(f"[{label}]", "Finish the current operation first."))
            return
        try:
            if dialog:
                async with self._dialog_lock:
                    await operation()
            else:
                await operation()
        except TimeoutError:
            self.push_log(
                Term.error(
                    f"[{label}]",
                    "Timed out waiting for server confirmation. Operation was not retried.",
                )
            )
        except Exception as error:
            self.push_log(Term.error(f"[{label}]", str(error) or type(error).__name__))

    async def action_quit(self) -> None:
        await self._close_resources()
        self.exit()

    async def _close_resources(self) -> None:
        if self._resources_closed:
            return
        self._resources_closed = True
        self.session.unsubscribe(self._session_event)
        workers = list(self.workers)
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*(worker.wait() for worker in workers), return_exceptions=True)
        await self.session.aclose()

    async def on_unmount(self) -> None:
        await self._close_resources()


def main() -> None:
    from fz_manager_plus.runtime import create_app

    create_app().run()


if __name__ == "__main__":
    main()
