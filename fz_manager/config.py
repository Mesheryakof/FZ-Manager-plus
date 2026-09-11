"""Shared application configuration.

A single place to collect settings for the whole `fz_manager` package (not
just the Factorio Zone prototype) as more of them show up. Values are
resolved from (highest priority first): CLI flags (`--...`), environment
variables (`FZM_...`), a `.env` file, then the defaults below -- CLI flags
always win, matching how `pydantic-settings` orders its default sources when
`cli_parse_args=True`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    factorio_zone_endpoint: str = "factorio.zone"
    max_mod_size: int = 268_435_456  # 256MB
    max_save_size: int = 100_663_296  # 96MB
    ws_ping_interval: float = 30
    ws_ping_timeout: float = 10
    storage_dir: Path | None = None
    user_token: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="FZM_",
        env_file=".env",
        cli_parse_args=True,
        cli_kebab_case=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Shared, process-wide `Settings` instance.

    Lazy: `Settings()` (and its `sys.argv` CLI parsing) only runs on the
    first actual call to `get_settings()`, not on import of this module --
    importing `fz_manager.config` anywhere (tests included) is always safe.
    Cached: every later call returns the same instance instead of
    re-parsing.

    Whichever code calls this *first* in the process is what `sys.argv`
    gets parsed against. That's fine from the real CLI entry point, but
    tests or embedding contexts with unrelated argv (e.g. pytest's own
    flags) should construct and pass their own `Settings(_cli_parse_args=False)`
    explicitly instead of relying on this default.
    """
    return Settings()
