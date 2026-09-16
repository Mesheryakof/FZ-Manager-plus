from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir

from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_STATE_DIR = Path(gettempdir()) / ".fzmp"
_STORE_PATH = _STATE_DIR / "settings.json"
CRASH_LOG_PATH = _STATE_DIR / "crash.log"


class Settings(BaseSettings):
    factorio_zone_endpoint: str = "factorio.zone"
    theme: str = 'gruvbox'
    max_mod_size: int = 268_435_456  # 256MB
    max_save_size: int = 100_663_296  # 96MB
    ws_ping_interval: float = 30
    ws_ping_timeout: float = 10
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
        cli_parse_args=True,
        cli_kebab_case=True,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls, json_file=_STORE_PATH),
            file_secret_settings,
        )

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        self._persist()

    def _persist(self) -> None:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(self.model_dump_json())


@lru_cache
def get_settings() -> Settings:
    return Settings()
