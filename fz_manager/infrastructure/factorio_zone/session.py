"""Session: owns Factorio Zone connection state synced from the WS message
stream, and wires REST (`FactorioZoneAPI`) + WS (`FactorioZoneSocket`)
together.

State fields and message-handling logic are ported from
`fz_manager.api.client.FZClient` -- specifically its `connect()` method's
`match data['type']` block, which this replaces with typed handlers
registered via `@FactorioZoneSocket.on(...)`. See that module for the
original, dict-based version.
"""

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
    """Owns synced connection state and drives the WS message loop.

    Composes `api` (REST) and `socket` (WS) -- both plain fields, no
    inheritance from either. See the module docstrings of
    `infrastructure/factorio_zone/client.py` / `socket.py` for why.
    """

    def __init__(self, api: FactorioZoneAPI, socket: FactorioZoneSocket):
        self.api = api
        self.socket = socket

        # -- Synced state, ported 1:1 from FZClient's attributes --
        self.user_token: str | None = None
        self.referrer_code: str | None = None
        self.regions: dict = {}
        self.versions: dict = {}
        self.saves: dict = {}
        self.mods: list = []
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
        """Opens the WS connection. Returns once connected -- does not
        process messages (see `run()`)."""
        await self.socket.connect()

    async def run(self) -> None:
        """Consumes the WS message stream forever, dispatching each message
        to the handlers registered below via `@FactorioZoneSocket.on(...)`.
        """
        await self.socket.listen(self)

    async def start_instance(self, region: str, version: str, save: str) -> None:
        await self.api.start_instance(region, version, save)

    async def stop_instance(self) -> None:
        """`launch_id` lives only on the session (set by the `starting`/
        `stopping`/`running`/`log` WS handlers below) -- `FactorioZoneAPI`
        doesn't track it itself, so it's passed in explicitly here rather
        than the REST layer reading it off its own state."""
        await self.api.stop_instance(self.launch_id)

    async def wait_sync(self) -> None:
        while not self.mods_sync or not self.saves_sync:
            await asyncio.sleep(1)

    async def send_command(self, command: str) -> None:
        await self.api.send_command(self.launch_id, command)

    # -- Mods, ported from the old `fz_manager.services.mods.ModsService` --
    # (its two network methods only; the filesystem-only staticmethods live
    # in `fz_manager.infrastructure.factorio_zone.mods` instead, since they
    # don't touch session/API state at all.)

    async def upload_mod(
        self, name: str, file, size: int, progress: Callable[[int], None] | None = None
    ) -> None:
        await self.api.upload_mod(name, file, size, progress)

    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        await self.api.toggle_mod(mod_id, enabled)

    async def delete_mod(self, mod_id: int) -> None:
        await self.api.delete_mod(mod_id)

    # -- Saves, ported from the old `fz_manager.services.saves.SavesService` --

    def used_save_slots(self) -> list[tuple[int, str]]:
        """(1-based slot index, description) pairs for slots that aren't
        empty. Ported from the old `SavesService.used_slots()`, but checking
        `.endswith("(empty)")` (like `is_save_slot_used()` below) instead of
        assuming slot order matches enumeration order 1:1 -- the old
        `slots()`/`used_slots()` pair only worked because both walked the
        same `dict.values()`, which this collapses into one method."""
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


# ---------------------------------------------------------------------------
# WS message handlers -- one per case of the old FZClient.connect()'s
# `match data['type']`. Plain functions, not methods: registering them
# doesn't need a FactorioZoneSession instance to exist yet (see
# utils/api_router/ws.py's module docstring for why).
# ---------------------------------------------------------------------------


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
    # Same de-dup as the old client: the server can resend a log line by
    # number, only emit it to listeners once.
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
    # An unrecognized `type` (see BlankMessage's docstring) -- log it
    # instead of silently dropping it, so a new/changed server event is
    # visible rather than invisible.
    await session._emit_log(Term.warn("warn", f"Unrecognized WS message: {message.model_dump()}"))
