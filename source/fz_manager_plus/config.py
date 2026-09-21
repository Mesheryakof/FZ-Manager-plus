"""Settings are values; loading, migration and persistence are explicit."""

import asyncio
import json
import os
import sys
import tempfile
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fz_manager_plus.utils.async_io import blocking_io

_stored: ContextVar[dict[str, Any] | None] = ContextVar("stored_settings", default=None)


def config_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "fz-manager-plus"
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "fz-manager-plus"
        )
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fz-manager-plus"


CRASH_LOG_PATH = config_directory() / "crash.log"


class Settings(BaseSettings):
    factorio_zone_endpoint: str = "factorio.zone"
    theme: str = "gruvbox"
    max_mod_size: int = Field(default=268_435_456, gt=0)
    max_save_size: int = Field(default=100_663_296, gt=0)
    sync_batch_size: int = Field(default=3, ge=1)
    ws_ping_interval: float = Field(default=30, gt=0)
    ws_ping_timeout: float = Field(default=10, gt=0)
    sync_timeout: float = Field(default=60, gt=0)
    start_timeout: float = Field(default=600, gt=0)
    stop_timeout: float = Field(default=3600, gt=0)
    storage_dir: Path | None = None
    user_token: str | None = None
    region: str | None = None
    version: str | None = None
    slot: str | None = None
    mods_path: str | None = None
    saves_path: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="FZM_",
        env_file=".env",
        cli_parse_args=False,
        cli_kebab_case=True,
        extra="ignore",
        validate_assignment=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            lambda: _stored.get() or {},
            file_secret_settings,
        )


class SettingsStore:
    def __init__(self, directory: Path | None = None, *, legacy_path: Path | None = None):
        self.directory = directory if directory is not None else config_directory()
        self.path = self.directory / "settings.json"
        self.crash_log_path = self.directory / "crash.log"
        self.server_log_path = self.directory / "server.log"
        self.legacy_path = legacy_path or Path(tempfile.gettempdir()) / ".fzmp" / "settings.json"
        self._lock = asyncio.Lock()

    def read(self) -> dict[str, Any]:
        source = self.path if self.path.exists() else self.legacy_path
        if not source.exists():
            return {}
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Settings must be a JSON object: {source}")
        return data

    def write(self, contents: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    async def save(self, settings: Settings) -> None:
        async with self._lock:
            await blocking_io(self.write, settings.model_dump_json())


def load_settings(
    argv: list[str] | None = None, *, store: SettingsStore | None = None
) -> tuple[Settings, SettingsStore]:
    arguments = sys.argv[1:] if argv is None else argv
    bootstrap = Settings(_cli_parse_args=arguments)
    store = store or SettingsStore(bootstrap.storage_dir)
    token = _stored.set(store.read())
    try:
        settings = Settings(_cli_parse_args=arguments)
    finally:
        _stored.reset(token)
    if not store.path.exists() and store.legacy_path.exists():
        store.write(settings.model_dump_json())
    return settings, store


@lru_cache
def get_settings() -> Settings:
    return load_settings()[0]
