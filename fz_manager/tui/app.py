"""Prototype Textual-based dashboard TUI for FZ-Manager.

This is an additive, standalone prototype living next to the existing
`questionary`/`prompt_toolkit` UI in `fz_manager/ui/`. It is NOT wired to the
`fzm`/`fz-manager` console entry points and does not implement full business
logic for menu items yet - see the module docstring in the task description
for scope.

Run it locally with:

    poetry run python -m fz_manager.tui.app

or, for Textual's live dev console (in a second terminal run
`poetry run textual console`, then in this one `poetry run textual run
--dev fz_manager.tui.app:FzManagerApp`).
"""

from __future__ import annotations

import asyncio

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ListItem, ListView, RichLog, Static

from fz_manager.config import Settings, get_settings
from fz_manager.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager.infrastructure.factorio_zone.session import FactorioZoneSession
from fz_manager.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager.terminal import Term
from fz_manager.tui.components import ChoiceScreen, ConfirmScreen, TokenScreen

STATIC_MENU_ITEMS = [
    "Manage mods",
    "Manage saves",
    "Exit",
]


class FzManagerApp(App):
    """Skeleton multi-pane dashboard: status bar + live log stream + menu."""

    TITLE = "Factorio Zone Manager"

    CSS = """
    Screen {
        layout: vertical;
    }

    #bottom-bar {
        dock: bottom;
        height: 2;
    }

    #status-bar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    #main-area {
        height: 1fr;
    }

    #log-pane {
        width: 3fr;
        border: solid $primary;
    }

    #log-view {
        height: 1fr;
    }

    #command-input {
        height: 3;
        border: none;
        border-top: solid $primary;
    }

    #menu-pane {
        width: 1fr;
        border: solid $secondary;
    }

    #menu-pane > ListView {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        # Falls back to a non-CLI-parsing Settings() by default -- safe for
        # tests/programmatic construction (see fz_manager.config.get_settings
        # for why). `main()` below passes a real `get_settings()` in, which
        # DOES parse `--user-token ...`/`FZM_USER_TOKEN`/`.env`, since that
        # call happens from the actual entry point where `sys.argv` is
        # legitimately what the user ran.
        self.settings = settings or Settings(_cli_parse_args=False)
        api = FactorioZoneAPI(self.settings)
        socket = FactorioZoneSocket(self.settings)
        self.session = FactorioZoneSession(api, socket)

    def _menu_items(self) -> list[str]:
        instance_item = "Stop server" if self.session.launch_id is not None else "Start server"
        return [instance_item, *STATIC_MENU_ITEMS]

    @property
    def main_screen(self):
        """The app's base screen, `#log-view`/`#main-menu`/`#status-bar`'s
        home. `self.query_one(...)` resolves against `self.screen` -- the
        currently ACTIVE one -- which is a modal (TokenScreen/ChoiceScreen/
        ConfirmScreen) whenever one is pushed. Background code (timers,
        the logs listener) runs regardless of which screen is active, so it
        must query this instead of `self`/`self.screen` to avoid a
        `NoMatches` crash the moment a modal is up when it fires.
        """
        return self.screen_stack[0]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-area"):
            with Vertical(id="log-pane"):
                yield RichLog(id="log-view", wrap=False, highlight=False, markup=False)
                yield Input(placeholder="Type a message and press Enter...", id="command-input")
            with Vertical(id="menu-pane"):
                yield ListView(
                    *[ListItem(Static(item), name=item) for item in self._menu_items()],
                    id="main-menu",
                )
        with Vertical(id="bottom-bar"):
            yield Static("Trial: N/A", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
        self.session.add_logs_listener(self.push_log)
        # `session.launch_id` isn't itself reactive (session.py has no
        # state-change-notification mechanism, only logs), so poll it --
        # same pattern as session.wait_sync()'s own polling.
        self.set_interval(1, self._refresh_status_bar)
        self.set_interval(1, self._refresh_menu)
        if self.settings.user_token:
            # Token already supplied programmatically (e.g. tests) -- skip
            # the prompt and connect right away.
            self._start_connecting()
        else:
            self.push_screen(TokenScreen(), self._on_token_submitted)

    def _on_token_submitted(self, token: str) -> None:
        self.settings.user_token = token or None
        self._start_connecting()

    def _start_connecting(self) -> None:
        log_view = self.main_screen.query_one("#log-view", RichLog)
        log_view.write(Text("Connecting to factorio.zone...", style="dim"))
        self.connect_client()

    def _refresh_status_bar(self) -> None:
        launch_id = self.session.launch_id
        status_bar = self.main_screen.query_one("#status-bar", Static)
        status_bar.update(f"Trial: N/A | Launch ID: {launch_id if launch_id is not None else '-'}")

    def _refresh_menu(self) -> None:
        menu = self.main_screen.query_one("#main-menu", ListView)
        desired = self._menu_items()
        current = [item.name for item in menu.children]
        if current == desired:
            return
        menu.clear()
        for item in desired:
            menu.append(ListItem(Static(item), name=item))

    @work(exclusive=True, group="ws-connect")
    async def connect_client(self) -> None:
        """Background worker: opens the real WebSocket connection and
        streams logs in for the lifetime of the session.

        Runs on the app's own asyncio event loop (Textual workers share it),
        so `push_log` below can safely touch the widget tree directly.
        """
        try:
            await self.session.connect()
            await self.session.run()
        except Exception as ex:  # noqa: BLE001 - never let a WS error crash the TUI
            self.push_log(Term.error("[connection error]", str(ex)))

    def push_log(self, *log: str) -> None:
        """Logs listener callback wired to `FactorioZoneSession.add_logs_listener`.

        `log` lines arrive pre-formatted with ANSI color codes (see
        `fz_manager.terminal.Term`), so we hand them to Rich's ANSI decoder
        via the custom `RichLog` widget rather than writing raw text.
        """
        if not log:
            return
        text = " ".join(log)
        log_view = self.main_screen.query_one("#log-view", RichLog)
        log_view.write(Text.from_ansi(text))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the command box. Just echoes into the log pane for now
        -- wiring this to a real `session.api.send_command(...)` call is a
        later step, once the app talks to a real, attached server.

        Guarded by id in case some other Input (e.g. TokenScreen's, which
        also calls `event.stop()` itself) ever ends up bubbling here.
        """
        if event.input.id != "command-input":
            return
        text = event.value.strip()
        if not text:
            return
        self.push_log(Term.info("COMMAND:", text))
        event.input.clear()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "main-menu":
            return
        if event.item.name == "Exit":
            self.exit()
        elif event.item.name == "Start server":
            self.start_server_flow()
        elif event.item.name == "Stop server":
            self.stop_server_flow()
        else:
            log_view = self.main_screen.query_one("#log-view", RichLog)
            log_view.write(
                Text(f"[menu] '{event.item.name}' is not implemented yet.", style="italic dim")
            )

    @work(exclusive=True, group="start-server")
    async def start_server_flow(self) -> None:
        """Region -> version -> save slot -> confirm -> start.

        Ported from the old `Main.start_server()` (see
        `fz_manager/ui/app.py`) and `InstanceService.start()`: same steps,
        same data sources (`session.regions`/`versions`/`saves`), same
        `f"slot{n}"` naming and running/server_address poll loop -- just
        driven by `ChoiceScreen`/`ConfirmScreen` modals instead of
        questionary `SelectMenu` prompts.
        """
        regions = sorted(self.session.regions.items())
        if not regions:
            self.push_log(Term.error("[start server]", "No regions available yet (still syncing?)"))
            return
        region = await self.push_screen_wait(
            ChoiceScreen("Choose a region:", [(f"{code} - {name}", code) for code, name in regions])
        )
        if region is None:
            return

        versions = list(self.session.versions)
        if not versions:
            self.push_log(
                Term.error("[start server]", "No versions available yet (still syncing?)")
            )
            return
        version = await self.push_screen_wait(
            ChoiceScreen("Choose a Factorio version:", [(v, v) for v in versions])
        )
        if version is None:
            return

        slots = list(self.session.saves.values())
        if not slots:
            self.push_log(
                Term.error("[start server]", "No save slots available yet (still syncing?)")
            )
            return
        slot = await self.push_screen_wait(
            ChoiceScreen(
                "Choose a save slot:", [(desc, str(i + 1)) for i, desc in enumerate(slots)]
            )
        )
        if slot is None:
            return

        confirmed = await self.push_screen_wait(
            ConfirmScreen(f"Start server in '{region}', version {version}, slot {slot}?")
        )
        if not confirmed:
            return

        self.push_log(Term.info("[start server]", "Starting instance..."))
        try:
            await self.session.start_instance(region, version, f"slot{slot}")
            while not self.session.running and not self.session.server_address:
                await asyncio.sleep(1)
            self.push_log(
                Term.info("[start server]", f"Server running at {self.session.server_address}")
            )
        except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
            self.push_log(Term.error("[start server]", str(ex)))

    @work(exclusive=True, group="stop-server")
    async def stop_server_flow(self) -> None:
        """Ported from the old `InstanceService.stop()`: call the API, then
        poll until the WS confirms the instance is no longer running."""
        self.push_log(Term.info("[stop server]", "Stopping instance..."))
        try:
            await self.session.stop_instance()
            while self.session.running:
                await asyncio.sleep(1)
            self.push_log(Term.info("[stop server]", "Instance stopped."))
        except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
            self.push_log(Term.error("[stop server]", str(ex)))

    async def action_quit(self) -> None:
        self.session.remove_logs_listener(self.push_log)
        self.exit()


def main() -> None:
    # Real entry point: sys.argv here is genuinely what the user typed to
    # launch this program, so parsing it (via get_settings()) is safe --
    # unlike everywhere else in this prototype, which avoids it.
    FzManagerApp(settings=get_settings()).run()


if __name__ == "__main__":
    main()
