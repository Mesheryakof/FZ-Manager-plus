import asyncio
import logging
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from inspect import isawaitable
from typing import TypeAlias, TypeVar

from fz_manager_plus.application.ports import ZoneAPI, ZoneSocket
from fz_manager_plus.config import Settings
from fz_manager_plus.domain.errors import AuthenticationError, DisconnectedError, OperationError
from fz_manager_plus.domain.messages import (
    BlankMessage,
    ConsoleMessage,
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
from fz_manager_plus.domain.state import (
    AuthenticationRequired,
    ConnectionStatus,
    LogEvent,
    Mod,
    ServerStatus,
    SessionEvent,
    SessionState,
    StateChanged,
    TokenReceived,
)

Listener: TypeAlias = Callable[[SessionEvent], Awaitable[None] | None]
T = TypeVar("T")
_ADDRESS = re.compile(r"selecting connection (\d+\.\d+\.\d+\.\d+:\d+)")
_LOG_LIMIT = 10_000
_logger = logging.getLogger(__name__)


class FactorioZoneSession:
    def __init__(self, api: ZoneAPI, socket: ZoneSocket, settings: Settings):
        self.api, self.socket, self.settings = api, socket, settings
        self.state = SessionState()
        self.user_token = api.user_token
        self._listeners: list[Listener] = []
        self._changed = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._disconnected.set()
        self._generation = 0
        self._closed = False
        self._runner: asyncio.Task | None = None
        self._operations: set[asyncio.Task] = set()
        self._logs: OrderedDict[tuple[object, int], None] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._ever_authenticated = False
        self._close_task: asyncio.Task | None = None

    @property
    def regions(self):
        return self.state.regions

    @property
    def versions(self):
        return self.state.versions

    @property
    def saves(self):
        return self.state.saves

    @property
    def mods(self):
        return self.state.mods

    @property
    def launch_id(self):
        return self.state.launch_id

    @property
    def server_status(self):
        return self.state.server_status

    @property
    def server_address(self):
        return self.state.server_address

    def subscribe(self, listener: Listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def emit(self, event: SessionEvent) -> None:
        for listener in tuple(self._listeners):
            try:
                result = listener(event)
                if isawaitable(result):
                    await result
            except Exception:
                # A broken observer must not tear down the transport.
                _logger.exception("Session event listener failed")

    async def _publish_state(self) -> None:
        self.state.revision += 1
        previous, self._changed = self._changed, asyncio.Event()
        previous.set()
        await self.emit(StateChanged(self.state.revision))

    async def _disconnect(self, status=ConnectionStatus.DISCONNECTED) -> None:
        self._disconnected.set()
        self.state.ready.clear()
        self.state.connection = status
        self.api.visit_secret = None
        await self._publish_state()

    async def connect(self) -> None:
        if self._closed:
            raise DisconnectedError("Session is closed")
        self._generation += 1
        self._disconnected = asyncio.Event()
        self.state.ready.clear()
        self.state.launch_id = None
        self.state.server_address = None
        self.state.connection = ConnectionStatus.CONNECTING
        await self._publish_state()
        async with asyncio.timeout(self.settings.sync_timeout):
            await self.socket.connect()
        self.state.connection = ConnectionStatus.SYNCING
        await self._publish_state()

    async def _consume(self) -> None:
        async for message in self.socket.messages():
            await self.handle_message(message)
        raise DisconnectedError("Connection closed by the server")

    async def _connected_run(self) -> None:
        consumer = asyncio.create_task(self._consume())
        ready = asyncio.create_task(self.wait_ready("auth", "mods", "saves", "server"))
        try:
            completed, _ = await asyncio.wait(
                (consumer, ready), return_when=asyncio.FIRST_COMPLETED
            )
            if consumer in completed:
                await consumer
            await ready
            await consumer
        finally:
            for task in (consumer, ready):
                task.cancel()
            await asyncio.gather(consumer, ready, return_exceptions=True)

    async def run(self) -> None:
        if self._runner is not None:
            raise RuntimeError("Session is already running")
        self._runner = asyncio.current_task()
        delay = 1
        try:
            while not self._closed:
                try:
                    await self.connect()
                    await self._connected_run()
                except AuthenticationError as error:
                    await self._disconnect(ConnectionStatus.AUTH_REQUIRED)
                    await self.emit(AuthenticationRequired(str(error)))
                    return
                except (DisconnectedError, OperationError, OSError, TimeoutError) as error:
                    was_ready = self.state.connection == ConnectionStatus.CONNECTED
                    await self._disconnect()
                    await self.emit(
                        LogEvent(
                            f"Connection lost: {error}. Retrying in {1 if was_ready else delay}s.",
                            "warn",
                        )
                    )
                    if was_ready:
                        delay = 1
                finally:
                    with suppress(Exception):
                        await self.socket.close()
                if not self._closed:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
        finally:
            if self.state.connection != ConnectionStatus.AUTH_REQUIRED:
                await self._disconnect()
            self._runner = None

    async def wait_for(self, predicate: Callable[[SessionState], bool], timeout: float) -> None:
        generation = self._generation
        async with asyncio.timeout(timeout):
            while True:
                changed = self._changed
                if self._closed or self._disconnected.is_set() or generation != self._generation:
                    raise DisconnectedError("Connection was interrupted; operation was not retried")
                if predicate(self.state):
                    return
                await changed.wait()

    async def wait_ready(self, *parts: str) -> None:
        await self.wait_for(lambda state: set(parts) <= state.ready, self.settings.sync_timeout)

    def require_ready(self, *parts: str) -> None:
        if self._closed or self._disconnected.is_set() or not {"auth", *parts} <= self.state.ready:
            raise DisconnectedError("Connection is not ready; wait for synchronization")

    async def _call(self, operation: Callable[[], Awaitable[T]]) -> T:
        self.require_ready()
        disconnected = self._disconnected

        async def execute() -> T:
            return await operation()

        task = asyncio.create_task(execute())
        lost = asyncio.create_task(disconnected.wait())
        self._operations.add(task)
        try:
            await asyncio.wait((task, lost), return_when=asyncio.FIRST_COMPLETED)
            if disconnected.is_set():
                raise DisconnectedError("Connection was interrupted; operation was not retried")
            return await task
        finally:
            task.cancel()
            lost.cancel()
            await asyncio.gather(task, lost, return_exceptions=True)
            self._operations.discard(task)

    @asynccontextmanager
    async def operation(self, resource: str, *ready: str):
        self.require_ready(*ready)
        generation = self._generation
        lock = self._locks.setdefault(resource, asyncio.Lock())
        async with lock:
            if generation != self._generation:
                raise DisconnectedError("Connection changed while the operation was waiting")
            self.require_ready(*ready)
            yield

    async def start_instance(self, region: str, version: str, save: str) -> None:
        async with self.operation("server", "server", "regions", "versions", "saves"):
            if self.state.server_status != ServerStatus.OFFLINE:
                raise OperationError("Server is already active")
            if region not in self.regions or version not in self.versions or save not in self.saves:
                raise OperationError("Server options changed; choose them again")
            async with asyncio.timeout(self.settings.start_timeout):
                await self._call(lambda: self.api.start_instance(region, version, save))
                await self.wait_for(
                    lambda state: (
                        state.server_status == ServerStatus.RUNNING and bool(state.server_address)
                    ),
                    self.settings.start_timeout,
                )

    async def stop_instance(self) -> None:
        async with self.operation("server", "server"):
            launch_id = self._launch_id()
            async with asyncio.timeout(self.settings.stop_timeout):
                await self._call(lambda: self.api.stop_instance(launch_id))
                await self.wait_for(
                    lambda state: state.server_status == ServerStatus.OFFLINE,
                    self.settings.stop_timeout,
                )

    def _launch_id(self) -> int:
        launch_id = self.launch_id
        if launch_id is None:
            raise OperationError("No running server")
        return launch_id

    async def send_command(self, command: str) -> None:
        self.require_ready("server")
        if self.server_status != ServerStatus.RUNNING:
            raise OperationError("Server is not running yet")
        launch_id = self._launch_id()
        await self._call(lambda: self.api.send_command(launch_id, command))

    async def toggle_mod(self, mod_id: int, enabled: bool) -> None:
        async with self.operation("mods", "mods"):
            await self._call(lambda: self.api.toggle_mod(mod_id, enabled))

    @asynccontextmanager
    async def mod_uploads(self):
        """Reserve mod mutations for a batch; uploads inside may run concurrently."""
        async with self.operation("mods", "mods"):
            generation = self._generation

            async def upload(name, file, size, progress=None):
                if generation != self._generation:
                    raise DisconnectedError("Connection changed; upload was not retried")
                await self._call(lambda: self.api.upload_mod(name, file, size, progress))

            yield upload

    async def delete_mod(self, mod_id: int) -> None:
        async with self.operation("mods", "mods"):
            await self._call(lambda: self.api.delete_mod(mod_id))

    async def delete_all_mods(self) -> None:
        async with self.operation("mods", "mods"):
            for mod in tuple(self.mods):
                try:
                    await self._call(lambda entry=mod: self.api.delete_mod(entry.id))
                    await self.emit(LogEvent(f"Deleted {mod.text}", "info"))
                except DisconnectedError:
                    raise
                except OperationError as error:
                    await self.emit(LogEvent(f"{mod.text}: {error}", "error"))

    def used_save_slots(self) -> list[tuple[int, str]]:
        return sorted(
            (int(slot.removeprefix("slot")), description)
            for slot, description in self.saves.items()
            if re.fullmatch(r"slot\d+", slot)
            and description
            and not description.endswith("(empty)")
        )

    def is_save_slot_used(self, slot_index: int) -> bool:
        description = self.saves.get(f"slot{slot_index}")
        return description is not None and bool(description) and not description.endswith("(empty)")

    def _check_slot(self, slot: str, *, used: bool = False) -> None:
        if slot not in self.saves or not re.fullmatch(r"slot\d+", slot):
            raise OperationError("Unknown save slot")
        if used and not self.is_save_slot_used(int(slot.removeprefix("slot"))):
            raise OperationError("Save slot is empty")

    async def upload_save(self, name, file, size, slot, progress=None) -> None:
        async with self.operation(f"save:{slot}", "saves"):
            self._check_slot(slot)
            await self._call(lambda: self.api.upload_save(name, file, size, slot, progress))

    async def delete_save_slot(self, slot: str) -> None:
        async with self.operation(f"save:{slot}", "saves"):
            self._check_slot(slot, used=True)
            await self._call(lambda: self.api.delete_save_slot(slot))

    async def download_save_slot(self, slot: str, file_path: str, progress=None) -> None:
        async with self.operation(f"save:{slot}", "saves"):
            self._check_slot(slot, used=True)
            await self._call(lambda: self.api.download_save_slot(slot, file_path, progress))

    async def handle_message(self, message) -> None:
        state = self.state
        match message:
            case VisitMessage():
                self.api.visit_secret = message.secret
                response = await self.api.login(reconnected=self._ever_authenticated)
                self._ever_authenticated = True
                self.user_token = response.user_token
                self.api.user_token = response.user_token
                state.ready.add("auth")
                await self.emit(TokenReceived(response.user_token))
            case OptionsMessage():
                options = message.options
                if message.name in ("regions", "saves"):
                    if not isinstance(options, dict) or not all(
                        isinstance(k, str) and isinstance(v, str) for k, v in options.items()
                    ):
                        await self.emit(LogEvent(f"Invalid {message.name} options", "warn"))
                        return
                    setattr(state, message.name, dict(options))
                    state.ready.add(message.name)
                elif message.name == "versions":
                    if not isinstance(options, (dict, list)) or not all(
                        isinstance(v, str) for v in options
                    ):
                        await self.emit(LogEvent("Invalid version options", "warn"))
                        return
                    state.versions = tuple(options)
                    state.ready.add("versions")
            case ModsMessage():
                state.mods = tuple(Mod(mod.id, mod.text, mod.enabled) for mod in message.mods)
                state.ready.add("mods")
            case IdleMessage():
                state.server_status = ServerStatus.OFFLINE
                state.launch_id = state.server_address = None
                state.ready.add("server")
            case StartingMessage() | StoppingMessage() | RunningMessage():
                previous = state.launch_id
                if message.launch_id is not None:
                    state.launch_id = message.launch_id
                if previous != state.launch_id:
                    state.server_address = None
                state.server_status = {
                    "starting": ServerStatus.STARTING,
                    "stopping": ServerStatus.STOPPING,
                    "running": ServerStatus.RUNNING,
                }[message.type]
                if isinstance(message, RunningMessage):
                    state.server_address = message.socket or state.server_address
                state.ready.add("server")
            case LogMessage():
                launch = message.launch_id if message.launch_id is not None else state.launch_id
                key = (
                    launch if launch is not None else f"connection:{self._generation}",
                    message.num,
                )
                if key in self._logs:
                    return
                self._logs[key] = None
                if len(self._logs) > _LOG_LIMIT:
                    self._logs.popitem(last=False)
                await self.emit(LogEvent(message.line or ""))
                if (
                    state.launch_id is None
                    and message.launch_id is not None
                    and state.server_status != ServerStatus.OFFLINE
                ):
                    state.launch_id = message.launch_id
                    await self._publish_state()
                return
            case InfoMessage() | WarnMessage() | ErrorMessage():
                line = message.line or ""
                if isinstance(message, InfoMessage) and (found := _ADDRESS.search(line)):
                    state.server_address = found[1]
                await self.emit(LogEvent(line, message.type))
            case BlankMessage():
                await self.emit(LogEvent(f"Unrecognized WS message type: {message.type}", "warn"))
                return
            case ConsoleMessage() | SlotMessage():
                # Console is an acknowledgement; save labels arrive through options.
                return
            case _:
                return
        if {"auth", "server", "mods", "saves"} <= state.ready:
            state.connection = ConnectionStatus.CONNECTED
        await self._publish_state()

    async def aclose(self) -> None:
        task = self._close_task
        if task is None:
            task = self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(task)

    async def _close(self) -> None:
        self._closed = True
        await self._disconnect()
        tasks = list(self._operations)
        runner = self._runner
        if runner is not None and runner is not asyncio.current_task():
            tasks.append(runner)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await self.socket.close()
        finally:
            await self.api.aclose()
