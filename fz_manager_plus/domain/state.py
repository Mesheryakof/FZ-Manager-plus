from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias


class ServerStatus(StrEnum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    RUNNING = "RUNNING"


class ConnectionStatus(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    SYNCING = "SYNCING"
    CONNECTED = "CONNECTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"


@dataclass(frozen=True)
class Mod:
    id: int
    text: str
    enabled: bool


@dataclass
class SessionState:
    connection: ConnectionStatus = ConnectionStatus.DISCONNECTED
    server_status: ServerStatus = ServerStatus.OFFLINE
    server_address: str | None = None
    launch_id: int | None = None
    regions: dict[str, str] = field(default_factory=dict)
    versions: tuple[str, ...] = ()
    saves: dict[str, str] = field(default_factory=dict)
    mods: tuple[Mod, ...] = ()
    ready: set[str] = field(default_factory=set)
    revision: int = 0


@dataclass(frozen=True)
class LogEvent:
    text: str
    level: str = "plain"


@dataclass(frozen=True)
class StateChanged:
    revision: int


@dataclass(frozen=True)
class TokenReceived:
    token: str


@dataclass(frozen=True)
class AuthenticationRequired:
    message: str


@dataclass(frozen=True)
class UploadItem:
    label: str
    size: int
    path: Path


@dataclass(frozen=True)
class TransferProgress:
    index: int
    bytes_done: int


@dataclass(frozen=True)
class TransferResult:
    index: int
    error: str | None = None


SessionEvent: TypeAlias = LogEvent | StateChanged | TokenReceived | AuthenticationRequired
TransferEvent: TypeAlias = TransferProgress | TransferResult
