"""Prototype Textual-based dashboard TUI for FZ-Manager.

This is an additive, standalone prototype living next to the existing
`questionary`/`prompt_toolkit` UI in `fz_manager/ui/`. It is NOT wired to the
`fzm`/`fz-manager` console entry points and does not implement full business
logic for menu items yet - see the module docstring in the task description
for scope.

`FzManagerApp` below owns application-level concerns only: session wiring,
top-level layout, and routing events between panes/modals. Each pane/modal
is a self-contained component (own `compose()`/CSS/behavior) living in
`fz_manager.tui.components`, mirroring a typical frontend `App` +
`components/` split.

Run it locally with:

    poetry run python -m fz_manager.tui.app

or, for Textual's live dev console (in a second terminal run
`poetry run textual console`, then in this one `poetry run textual run
--dev fz_manager.tui.app:FzManagerApp`).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from os import path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ListView

from fz_manager.config import Settings, get_settings
from fz_manager.infrastructure.factorio_zone import mods
from fz_manager.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager.infrastructure.factorio_zone.session import FactorioZoneSession
from fz_manager.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager.storage import Storage
from fz_manager.terminal import Term
from fz_manager.tui.components import (
    STATIC_MENU_ITEMS,
    ChoiceScreen,
    ConfirmScreen,
    LogPane,
    MenuPane,
    MultiChoiceScreen,
    PathScreen,
    StatusBar,
    TokenScreen,
)


class FzManagerApp(App):
    """Skeleton multi-pane dashboard: status bar + live log stream + menu."""

    TITLE = "Factorio Zone Manager"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-area {
        height: 1fr;
    }

    #bottom-bar {
        dock: bottom;
        height: 2;
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
        # Same on-disk JSON store + prompt_toolkit FileHistory files the old
        # UI used (fz_manager/storage.py, untouched) -- just consumed
        # differently here: single last-value get()/store() instead of
        # cycling through FileHistory with Up/Down, since Textual's Input
        # doesn't have prompt_toolkit's buffer history built in.
        self.storage = Storage()

    def _menu_items(self) -> list[str]:
        instance_item = "Stop server" if self.session.launch_id is not None else "Start server"
        return [instance_item, *STATIC_MENU_ITEMS]

    @property
    def main_screen(self):
        """The app's base screen, `LogPane`/`MenuPane`/`StatusBar`'s home.
        `self.query_one(...)` resolves against `self.screen` -- the
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
            yield LogPane(id="log-pane")
            yield MenuPane(self._menu_items(), id="menu-pane")
        with Vertical(id="bottom-bar"):
            yield StatusBar("Trial: N/A", id="status-bar")
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
            self.push_screen(
                TokenScreen(default=self.storage.get("userToken") or ""), self._on_token_submitted
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

    def _refresh_menu(self) -> None:
        self.main_screen.query_one(MenuPane).sync_items(self._menu_items())

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
        self.main_screen.query_one(LogPane).log_view.write(Text.from_ansi(text))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the command box: sends the command to the attached,
        running server -- the new TUI's equivalent of the old `Shell`
        ("Attach to server") screen, folded into the always-visible command
        box instead of a separate full-screen mode, since the widgets are
        already on screen either way.

        Guarded by id in case some other Input (e.g. TokenScreen's, which
        also calls `event.stop()` itself) ever ends up bubbling here.
        """
        if event.input.id != "command-input":
            return
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        if self.session.launch_id is None:
            self.push_log(Term.error("COMMAND:", "No running server to attach to."))
            return
        self.push_log(Term.info("COMMAND:", text))
        self.send_command(text)

    @work(group="send-command")
    async def send_command(self, command: str) -> None:
        try:
            await self.session.send_command(command)
        except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
            self.push_log(Term.error("[command]", str(ex)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "main-menu":
            return
        if event.item.name == "Exit":
            self.exit()
        elif event.item.name == "Start server":
            self.start_server_flow()
        elif event.item.name == "Stop server":
            self.stop_server_flow()
        elif event.item.name == "Manage mods":
            self.manage_mods_flow()
        elif event.item.name == "Manage saves":
            self.manage_saves_flow()
        else:
            self.main_screen.query_one(LogPane).log_view.write(
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
            ChoiceScreen(
                "Choose a region:",
                [(f"{code} - {name}", code) for code, name in regions],
                default=self.storage.get("region"),
            )
        )
        if region is None:
            return
        self.storage.store("region", region)

        versions = list(self.session.versions)
        if not versions:
            self.push_log(
                Term.error("[start server]", "No versions available yet (still syncing?)")
            )
            return
        version = await self.push_screen_wait(
            ChoiceScreen(
                "Choose a Factorio version:",
                [(v, v) for v in versions],
                default=self.storage.get("version"),
            )
        )
        if version is None:
            return
        self.storage.store("version", version)

        slots = list(self.session.saves.values())
        if not slots:
            self.push_log(
                Term.error("[start server]", "No save slots available yet (still syncing?)")
            )
            return
        slot = await self.push_screen_wait(
            ChoiceScreen(
                "Choose a save slot:",
                [(desc, str(i + 1)) for i, desc in enumerate(slots)],
                default=self.storage.get("slot"),
            )
        )
        if slot is None:
            return
        self.storage.store("slot", slot)

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
            self.storage.persist()
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

    def _progress_logger(self, label: str, total: float | None) -> Callable[[int], None]:
        """Builds a throttled upload/download progress callback: logs at
        25/50/75/100% instead of once per chunk read (`UploadProgressFile`/
        `download_save_slot` call back far more often than that).

        Replaces the old `rich.progress.Progress` bars -- those print
        straight to the terminal, which fights Textual for control of the
        screen buffer and can't be used from inside a running Textual app;
        log lines through the existing `push_log`/`RichLog` pipe instead.
        """
        reported: set[int] = set()

        def on_progress(bytes_done: int) -> None:
            if not total:
                return
            step = min(100, int(bytes_done * 100 / total) // 25 * 25)
            if step and step not in reported:
                reported.add(step)
                self.push_log(Term.info(label, f"{step}%"))

        return on_progress

    @work(exclusive=True, group="manage-mods")
    async def manage_mods_flow(self) -> None:
        """"Manage mods" submenu -- ported from the old `Main.manage_mods_menu()`
        loop (create mod-settings.zip / upload / enable-disable / delete),
        just driven by `ChoiceScreen` instead of a nested questionary
        `ActionMenu`."""
        while True:
            action = await self.push_screen_wait(
                ChoiceScreen(
                    "Manage mods:",
                    [
                        ("Create mod-settings.zip", "create-mod-settings"),
                        ("Upload mods", "upload-mods"),
                        ("Enable/Disable uploaded mods", "toggle-mods"),
                        ("Delete uploaded mods", "delete-mods"),
                        ("Back", "back"),
                    ],
                )
            )
            if action is None or action == "back":
                return
            if action == "create-mod-settings":
                await self._create_mod_settings()
            elif action == "upload-mods":
                await self._upload_mods()
            elif action == "toggle-mods":
                await self._toggle_mods()
            elif action == "delete-mods":
                await self._delete_mods()

    async def _create_mod_settings(self) -> None:
        mods_folder = await self.push_screen_wait(
            PathScreen(
                "Insert path to mods folder:",
                default=self.storage.get("modsPath") or "",
                validator=lambda p: path.isdir(p),
                error_message="Not a directory.",
            )
        )
        if mods_folder is None:
            return
        self.storage.store("modsPath", mods_folder)

        try:
            mod_settings_zip_path = mods.create_mod_settings_zip(mods_folder)
        except FileNotFoundError as ex:
            self.push_log(Term.error("[manage mods]", str(ex)))
            return
        self.push_log(Term.info("[manage mods]", f"{mod_settings_zip_path} created"))

    async def _upload_mods(self) -> None:
        mods_folder = await self.push_screen_wait(
            PathScreen(
                "Insert path to mods folder:",
                default=self.storage.get("modsPath") or "",
                validator=lambda p: path.exists(p),
                error_message="Path does not exist.",
            )
        )
        if mods_folder is None:
            return
        self.storage.store("modsPath", mods_folder)

        root, zip_names = mods.list_zip_files(mods_folder)
        if not zip_names:
            self.push_log(Term.error("[upload mods]", "No mod found in folder"))
            return

        selected = await self.push_screen_wait(
            MultiChoiceScreen(
                "Choose mods to upload:", [(name, name) for name in zip_names], preselected=zip_names
            )
        )
        if not selected:
            return

        for mod_file in mods.build_mod_files(root, selected):
            self.push_log(Term.info("[upload mods]", f"Uploading {mod_file.name}..."))
            try:
                with open(mod_file.file_path, "rb") as fh:
                    await self.session.upload_mod(
                        mod_file.name,
                        fh,
                        mod_file.size,
                        self._progress_logger(f"[upload mods] {mod_file.name}", mod_file.size),
                    )
                self.push_log(Term.info("[upload mods]", f"{mod_file.name}: done"))
            except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
                self.push_log(Term.error("[upload mods]", f"{mod_file.name}: {ex}"))

    async def _toggle_mods(self) -> None:
        if not self.session.mods:
            self.push_log(Term.error("[manage mods]", "No uploaded mods found"))
            return

        options = [(m["text"], str(m["id"])) for m in self.session.mods]
        preselected = [str(m["id"]) for m in self.session.mods if m["enabled"]]
        selected = await self.push_screen_wait(
            MultiChoiceScreen("Enable/Disable mods:", options, preselected=preselected)
        )
        if selected is None:
            return

        added = set(selected) - set(preselected)
        removed = set(preselected) - set(selected)
        for mod_id in added:
            self.push_log(Term.info("[manage mods]", f"Enabling mod {mod_id}"))
            await self.session.toggle_mod(int(mod_id), True)
        for mod_id in removed:
            self.push_log(Term.info("[manage mods]", f"Disabling mod {mod_id}"))
            await self.session.toggle_mod(int(mod_id), False)

    async def _delete_mods(self) -> None:
        if not self.session.mods:
            self.push_log(Term.error("[manage mods]", "No uploaded mods found"))
            return

        options = [(m["text"], str(m["id"])) for m in self.session.mods]
        selected = await self.push_screen_wait(
            MultiChoiceScreen("Delete mods:", options, preselected=[])
        )
        if not selected:
            return
        confirmed = await self.push_screen_wait(ConfirmScreen(f"Delete {len(selected)} mod(s)?"))
        if not confirmed:
            return
        for mod_id in selected:
            self.push_log(Term.info("[manage mods]", f"Deleting mod {mod_id}"))
            await self.session.delete_mod(int(mod_id))

    @work(exclusive=True, group="manage-saves")
    async def manage_saves_flow(self) -> None:
        """"Manage saves" submenu -- ported from the old
        `Main.manage_saves_menu()` loop (upload / delete / download),
        same structure as `manage_mods_flow` above."""
        while True:
            action = await self.push_screen_wait(
                ChoiceScreen(
                    "Manage saves:",
                    [
                        ("Upload save", "upload-save"),
                        ("Delete save", "delete-save"),
                        ("Download save", "download-save"),
                        ("Back", "back"),
                    ],
                )
            )
            if action is None or action == "back":
                return
            if action == "upload-save":
                await self._upload_save()
            elif action == "delete-save":
                await self._delete_save()
            elif action == "download-save":
                await self._download_save()

    async def _upload_save(self) -> None:
        file_path = await self.push_screen_wait(
            PathScreen(
                "Insert path to save file:",
                default=self.storage.get("savesPath") or "",
                validator=lambda p: path.exists(p) and path.splitext(p)[1] == ".zip",
                error_message="Save file must be an existing .zip archive.",
            )
        )
        if file_path is None:
            return
        self.storage.store("savesPath", file_path)

        slot_choice = await self.push_screen_wait(
            ChoiceScreen("Choose a save slot:", [(f"slot {i}", str(i)) for i in range(1, 10)])
        )
        if slot_choice is None:
            return
        slot_index = int(slot_choice)
        slot_name = f"slot{slot_index}"

        if self.session.is_save_slot_used(slot_index):
            confirmed = await self.push_screen_wait(
                ConfirmScreen(f"Slot {slot_index} is already used, do you want to replace it?")
            )
            if not confirmed:
                return
            await self.session.delete_save_slot(slot_name)

        filename = path.basename(file_path)
        size = path.getsize(file_path)
        self.push_log(Term.info("[upload save]", f"Uploading {filename}..."))
        try:
            with open(file_path, "rb") as fh:
                await self.session.upload_save(
                    filename, fh, size, slot_name, self._progress_logger("[upload save]", size)
                )
            self.push_log(Term.info("[upload save]", "Done."))
        except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
            self.push_log(Term.error("[upload save]", str(ex)))

    async def _delete_save(self) -> None:
        slots = self.session.used_save_slots()
        if not slots:
            self.push_log(Term.error("[delete save]", "All the slots are empty"))
            return

        options = [(description, str(index)) for index, description in slots]
        selected = await self.push_screen_wait(
            MultiChoiceScreen("Select slots to delete:", options, preselected=[])
        )
        if not selected:
            return
        confirmed = await self.push_screen_wait(ConfirmScreen(f"Delete {len(selected)} slot(s)?"))
        if not confirmed:
            return

        for slot_index in selected:
            self.push_log(Term.info("[delete save]", f"Deleting slot {slot_index}"))
            try:
                await self.session.delete_save_slot(f"slot{slot_index}")
            except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
                self.push_log(Term.error("[delete save]", str(ex)))

    async def _download_save(self) -> None:
        slots = self.session.used_save_slots()
        if not slots:
            self.push_log(Term.error("[download save]", "All the slots are empty"))
            return

        options = [(description, str(index)) for index, description in slots]
        selected = await self.push_screen_wait(
            MultiChoiceScreen("Select slots to download:", options, preselected=[])
        )
        if not selected:
            return

        directory = await self.push_screen_wait(
            PathScreen(
                "Insert download directory path:",
                default=self.storage.get("savesPath") or "",
                validator=lambda p: path.isdir(p),
                error_message="Not a directory.",
            )
        )
        if directory is None:
            return
        self.storage.store("savesPath", directory)

        descriptions = dict(slots)
        for slot_index in selected:
            slot_int = int(slot_index)
            slot_name = f"slot{slot_int}"
            description = descriptions.get(slot_int, "")
            # Slot descriptions look like "slot 2 - 12.34MB" -- same size
            # parsing the old `download_save_menu()` used to size the
            # progress bar; here it just scales the 25/50/75/100% log steps.
            size_match = re.search(r"(\d+\.\d+)MB", description)
            expected_size = float(size_match[1]) * 1048576 if size_match else None

            target = path.join(directory, f"slot{slot_int}.zip")
            self.push_log(Term.info("[download save]", f"Downloading slot {slot_int}..."))
            try:
                await self.session.download_save_slot(
                    slot_name, target, self._progress_logger(f"[download save] slot {slot_int}", expected_size)
                )
                self.push_log(Term.info("[download save]", f"Slot {slot_int}: done"))
            except Exception as ex:  # noqa: BLE001 - report, don't crash the TUI
                self.push_log(Term.error("[download save]", str(ex)))

    async def action_quit(self) -> None:
        self.session.remove_logs_listener(self.push_log)
        if self.session.user_token:
            # `session.user_token` is only set once the WS `visit` handler's
            # login round-trip completes (see session.py), so it may still
            # be unset on a very early quit -- nothing to persist then.
            self.storage.store("userToken", self.session.user_token)
        self.storage.persist()
        self.exit()


def main() -> None:
    # Real entry point: sys.argv here is genuinely what the user typed to
    # launch this program, so parsing it (via get_settings()) is safe --
    # unlike everywhere else in this prototype, which avoids it.
    FzManagerApp(settings=get_settings()).run()


if __name__ == "__main__":
    main()
