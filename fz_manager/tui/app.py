from __future__ import annotations

import asyncio
import re
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from os import path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

from fz_manager.config import CRASH_LOG_PATH, Settings, get_settings
from fz_manager.infrastructure.factorio_zone import mods
from fz_manager.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager.infrastructure.factorio_zone.session import FactorioZoneSession
from fz_manager.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager.terminal import Term
from fz_manager.tui.components import (
    ChoiceScreen,
    ConfirmScreen,
    LogPane,
    MenuPane,
    ModsPane,
    MultiChoiceScreen,
    PathScreen,
    SelectableList,
    StatusBar,
    TokenScreen,
)

STATIC_MENU_ITEMS = [
    "Manage mods",
    "Manage saves",
    "Exit",
]


class FzManagerApp(App):
    TITLE = "Factorio Zone Manager"

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
        height: 2;
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

    def _handle_exception(self, error: Exception) -> None:
        # App.run() swallows exceptions internally (renders Textual's own
        # crash screen, returns normally) instead of re-raising them, so a
        # try/except around app.run() in main() would never fire -- this is
        # the actual hook Textual calls with the unhandled exception, before
        # it does anything else with it.
        #
        # A @work-decorated method's exception arrives wrapped in a
        # WorkerFailed (textual/worker.py), whose own __traceback__ only
        # points at Textual's worker-scheduling code, not the actual bug --
        # the real traceback lives on WorkerFailed.error. Chain it via
        # __cause__ so traceback.print_exception includes both.
        wrapped = getattr(error, "error", None)
        if isinstance(wrapped, BaseException) and error.__cause__ is None:
            error.__cause__ = wrapped

        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG_PATH, "a") as fh:
            fh.write(f"\n--- {datetime.now(timezone.utc).isoformat()} ---\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=fh)
        super()._handle_exception(error)

    def _menu_items(self) -> list[str]:
        instance_item = "Stop server" if self.session.launch_id is not None else "Start server"
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
        with Vertical(id="bottom-bar"):
            yield StatusBar("Trial: N/A", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
        self.session.add_logs_listener(self.push_log)
        self.set_interval(1, self._refresh_status_bar)
        self.set_interval(1, self._refresh_menu)
        self.set_interval(1, self._refresh_mods)
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
        self.push_log(Term.info("COMMAND:", text))
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
        if event.value == "Exit":
            self.exit()
        elif event.value == "Start server":
            self.start_server_flow()
        elif event.value == "Stop server":
            self.stop_server_flow()
        elif event.value == "Manage mods":
            self.manage_mods_flow()
        elif event.value == "Manage saves":
            self.manage_saves_flow()
        else:
            self.main_screen.query_one(LogPane).log_view.write(
                Text(f"[menu] '{event.value}' is not implemented yet.", style="italic dim")
            )

    def on_mods_pane_toggled(self, event: ModsPane.Toggled) -> None:
        self.toggle_mod(event.mod_id, event.enabled)

    @work(group="toggle-mod")
    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        try:
            await self.session.toggle_mod(mod_id, enabled)
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[manage mods]", str(ex)))

    def on_mods_pane_delete_requested(self, event: ModsPane.DeleteRequested) -> None:
        self.delete_mod_flow(event.mod_id)

    @work(exclusive=False, group="delete-mod")
    async def delete_mod_flow(self, mod_id: int) -> None:
        name = next((m.text for m in self.session.mods if m.id == mod_id), str(mod_id))
        confirmed = await self.push_screen_wait(ConfirmScreen(f"Delete mod '{name}'?"))
        if not confirmed:
            return
        try:
            await self.session.delete_mod(mod_id)
            self.push_log(Term.info("[manage mods]", f"Deleted {name}"))
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[manage mods]", str(ex)))

    @work(exclusive=True, group="start-server")
    async def start_server_flow(self) -> None:
        regions = sorted(self.session.regions.items())
        if not regions:
            self.push_log(Term.error("[start server]", "No regions available yet (still syncing?)"))
            return
        region = await self.push_screen_wait(
            ChoiceScreen(
                "Choose a region:",
                [(f"{code} - {name}", code) for code, name in regions],
                default=self.settings.region,
            )
        )
        if region is None:
            return
        self.settings.region = region

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
                default=self.settings.version,
            )
        )
        if version is None:
            return
        self.settings.version = version

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
                default=self.settings.slot,
            )
        )
        if slot is None:
            return
        self.settings.slot = slot

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
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[start server]", str(ex)))

    @work(exclusive=True, group="stop-server")
    async def stop_server_flow(self) -> None:
        self.push_log(Term.info("[stop server]", "Stopping instance..."))
        try:
            await self.session.stop_instance()
            while self.session.running:
                await asyncio.sleep(1)
            self.push_log(Term.info("[stop server]", "Instance stopped."))
        except Exception as ex:  # noqa: BLE001
            self.push_log(Term.error("[stop server]", str(ex)))

    def _progress_logger(self, label: str, total: float | None) -> Callable[[int], None]:
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
                default=self.settings.mods_path or "",
                validator=lambda p: path.isdir(p),
                error_message="Not a directory.",
            )
        )
        if mods_folder is None:
            return
        self.settings.mods_path = mods_folder

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
                default=self.settings.mods_path or "",
                validator=lambda p: path.exists(p),
                error_message="Path does not exist.",
            )
        )
        if mods_folder is None:
            return
        self.settings.mods_path = mods_folder

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
            except Exception as ex:  # noqa: BLE001
                self.push_log(Term.error("[upload mods]", f"{mod_file.name}: {ex}"))

    async def _toggle_mods(self) -> None:
        if not self.session.mods:
            self.push_log(Term.error("[manage mods]", "No uploaded mods found"))
            return

        options = [(m.text, str(m.id)) for m in self.session.mods]
        preselected = [str(m.id) for m in self.session.mods if m.enabled]
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

        options = [(m.text, str(m.id)) for m in self.session.mods]
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
                default=self.settings.saves_path or "",
                validator=lambda p: path.exists(p) and path.splitext(p)[1] == ".zip",
                error_message="Save file must be an existing .zip archive.",
            )
        )
        if file_path is None:
            return
        self.settings.saves_path = file_path

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
        except Exception as ex:  # noqa: BLE001
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
            except Exception as ex:  # noqa: BLE001
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
                default=self.settings.saves_path or "",
                validator=lambda p: path.isdir(p),
                error_message="Not a directory.",
            )
        )
        if directory is None:
            return
        self.settings.saves_path = directory

        descriptions = dict(slots)
        for slot_index in selected:
            slot_int = int(slot_index)
            slot_name = f"slot{slot_int}"
            description = descriptions.get(slot_int, "")
            size_match = re.search(r"(\d+\.\d+)MB", description)
            expected_size = float(size_match[1]) * 1048576 if size_match else None

            target = path.join(directory, f"slot{slot_int}.zip")
            self.push_log(Term.info("[download save]", f"Downloading slot {slot_int}..."))
            try:
                await self.session.download_save_slot(
                    slot_name, target, self._progress_logger(f"[download save] slot {slot_int}", expected_size)
                )
                self.push_log(Term.info("[download save]", f"Slot {slot_int}: done"))
            except Exception as ex:  # noqa: BLE001
                self.push_log(Term.error("[download save]", str(ex)))

    async def action_quit(self) -> None:
        self.session.remove_logs_listener(self.push_log)
        if self.session.user_token:
            self.settings.user_token = self.session.user_token
        self.exit()


def main() -> None:
    FzManagerApp(settings=get_settings()).run()


if __name__ == "__main__":
    main()
