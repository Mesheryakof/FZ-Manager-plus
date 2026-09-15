import asyncio
import re
from collections.abc import Callable, Coroutine
from inspect import iscoroutinefunction
from typing import Any

from fz_manager.infrastructure.factorio_zone.client import FactorioZoneAPI
from fz_manager.infrastructure.factorio_zone.models import (
    BlankMessage,
    ErrorMessage,
    IdleMessage,
    InfoMessage,
    LogMessage,
    ModEntry,
    ModsMessage,
    OptionsMessage,
    RunningMessage,
    SlotMessage,
    StartingMessage,
    StoppingMessage,
    VisitMessage,
    WarnMessage,
)
from fz_manager.infrastructure.factorio_zone.socket import FactorioZoneSocket
from fz_manager.terminal import Term

LogListener = Callable[[str], Coroutine[Any, Any, None] | None]


class ServerStatus:
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    RUNNING = "RUNNING"


class FactorioZoneSession:
    def __init__(self, api: FactorioZoneAPI, socket: FactorioZoneSocket):
        self.api = api
        self.socket = socket

        self.user_token: str | None = None
        self.referrer_code: str | None = None
        self.regions: dict = {}
        self.versions: dict = {}
        self.saves: dict = {}
        self.mods: list[ModEntry] = []
        self.slots: dict = {}
        self.running: bool = False
        self.server_status: str = ServerStatus.OFFLINE
        self.server_address: str | None = None
        self.mods_sync: bool = False
        self.saves_sync: bool = False
        self.launch_id: int | None = None

        self._logs_map: dict = {}
        self._log_listeners: list[LogListener] = []

    async def connect(self) -> None:
        await self.socket.connect()

    async def run(self) -> None:
        await self.socket.listen(self)

    async def start_instance(self, region: str, version: str, save: str) -> None:
        await self.api.start_instance(region, version, save)

    async def stop_instance(self) -> None:
        await self.api.stop_instance(self.launch_id)

    async def wait_sync(self) -> None:
        while not self.mods_sync or not self.saves_sync:
            await asyncio.sleep(1)

    async def send_command(self, command: str) -> None:
        await self.api.send_command(self.launch_id, command)

    async def upload_mod(
        self, name: str, file, size: int, progress: Callable[[int], None] | None = None
    ) -> None:
        await self.api.upload_mod(name, file, size, progress)

    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        await self.api.toggle_mod(mod_id, enabled)

    async def delete_mod(self, mod_id: int) -> None:
        await self.api.delete_mod(mod_id)

    def used_save_slots(self) -> list[tuple[int, str]]:
        return [
            (i + 1, description)
            for i, description in enumerate(self.saves.values())
            if not description.endswith("(empty)")
        ]

    def is_save_slot_used(self, slot_index: int) -> bool:
        description = self.saves.get(f"slot{slot_index}", "")
        return not description.endswith("(empty)")

    async def upload_save(
        self, name: str, file, size: int, slot: str, progress: Callable[[int], None] | None = None
    ) -> None:
        await self.api.upload_save(name, file, size, slot, progress)

    async def delete_save_slot(self, slot: str) -> None:
        await self.api.delete_save_slot(slot)

    async def download_save_slot(
        self, slot: str, file_path: str, progress: Callable[[int], None] | None = None
    ) -> None:
        await self.api.download_save_slot(slot, file_path, progress)

    def add_logs_listener(self, listener: LogListener) -> None:
        self._log_listeners.append(listener)

    def remove_logs_listener(self, listener: LogListener) -> None:
        self._log_listeners.remove(listener)

    async def _emit_log(self, line: str | None) -> None:
        for listener in self._log_listeners:
            if iscoroutinefunction(listener):
                await listener(line)
            else:
                listener(line)


@FactorioZoneSocket.on(VisitMessage)
async def _handle_visit(session: FactorioZoneSession, message: VisitMessage) -> None:
    session.api.visit_secret = message.secret
    response = await session.api.login()
    session.user_token = response.user_token
    session.referrer_code = response.referral_code


@FactorioZoneSocket.on(OptionsMessage)
async def _handle_options(session: FactorioZoneSession, message: OptionsMessage) -> None:
    match message.name:
        case "regions":
            session.regions = message.options
        case "versions":
            session.versions = message.options
        case "saves":
            session.saves = message.options
            session.saves_sync = True


@FactorioZoneSocket.on(ModsMessage)
async def _handle_mods(session: FactorioZoneSession, message: ModsMessage) -> None:
    session.mods = message.mods
    session.mods_sync = True


@FactorioZoneSocket.on(IdleMessage)
async def _handle_idle(session: FactorioZoneSession, message: IdleMessage) -> None:
    session.running = False
    session.launch_id = None
    session.server_status = ServerStatus.OFFLINE
    session.server_address = None


@FactorioZoneSocket.on(StartingMessage)
async def _handle_starting(session: FactorioZoneSession, message: StartingMessage) -> None:
    session.running = True
    session.launch_id = message.launch_id
    session.server_status = ServerStatus.STARTING


@FactorioZoneSocket.on(StoppingMessage)
async def _handle_stopping(session: FactorioZoneSession, message: StoppingMessage) -> None:
    session.running = True
    session.launch_id = message.launch_id
    session.server_status = ServerStatus.STOPPING


@FactorioZoneSocket.on(RunningMessage)
async def _handle_running(session: FactorioZoneSession, message: RunningMessage) -> None:
    session.running = True
    session.launch_id = message.launch_id
    session.server_address = message.socket
    session.server_status = ServerStatus.RUNNING


@FactorioZoneSocket.on(SlotMessage)
async def _handle_slot(session: FactorioZoneSession, message: SlotMessage) -> None:
    session.slots[message.slot] = message


@FactorioZoneSocket.on(LogMessage)
async def _handle_log(session: FactorioZoneSession, message: LogMessage) -> None:
    if message.num in session._logs_map:
        return
    session._logs_map[message.num] = message.num
    if message.launch_id:
        session.launch_id = message.launch_id
    await session._emit_log(message.line)


@FactorioZoneSocket.on(InfoMessage)
async def _handle_info(session: FactorioZoneSession, message: InfoMessage) -> None:
    line = message.line or ""
    found = re.compile(r"selecting connection (\d+\.\d+\.\d+\.\d+:\d+)").findall(line)
    if found:
        session.server_address = found[0]
        session.server_status = ServerStatus.STARTING
    await session._emit_log(Term.info("info", line))


@FactorioZoneSocket.on(WarnMessage)
async def _handle_warn(session: FactorioZoneSession, message: WarnMessage) -> None:
    await session._emit_log(Term.warn("warn", message.line))


@FactorioZoneSocket.on(ErrorMessage)
async def _handle_error(session: FactorioZoneSession, message: ErrorMessage) -> None:
    await session._emit_log(Term.error("error", message.line))


@FactorioZoneSocket.on(BlankMessage)
async def _handle_blank(session: FactorioZoneSession, message: BlankMessage) -> None:
    await session._emit_log(Term.warn("warn", f"Unrecognized WS message: {message.model_dump()}"))
