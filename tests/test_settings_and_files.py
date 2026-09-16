import asyncio
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from fz_manager_plus.config import Settings, SettingsStore, config_directory, load_settings
from fz_manager_plus.infrastructure.factorio_zone.mods import create_mod_settings_zip
from fz_manager_plus.utils.files import find_by_extension


def test_settings_assignment_has_no_io_and_save_is_explicit(tmp_path):
    store = SettingsStore(tmp_path, legacy_path=tmp_path / "absent")
    settings = Settings(_env_file=None)
    settings.user_token = "test-token"
    assert not store.path.exists()
    asyncio.run(store.save(settings))
    assert json.loads(store.path.read_text())["user_token"] == "test-token"
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [store.path]


def test_settings_precedence_and_one_time_migration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"region": "legacy", "user_token": "old-token", "slot": "3"}))
    store = SettingsStore(tmp_path / "new", legacy_path=legacy)
    monkeypatch.setenv("FZM_REGION", "environment")
    settings, _ = load_settings(["--region", "cli"], store=store)
    assert settings.region == "cli"
    assert settings.user_token == "old-token"
    assert settings.slot == "3"
    assert legacy.exists() and store.path.exists()
    legacy.write_text('{"user_token": "do-not-import"}')
    assert load_settings([], store=store)[0].user_token == "old-token"
    assert load_settings([], store=store)[0].region == "environment"
    monkeypatch.delenv("FZM_REGION")
    (tmp_path / ".env").write_text("FZM_REGION=dotenv\n")
    assert load_settings([], store=store)[0].region == "dotenv"


def test_storage_dir_cli_override_and_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "chosen"
    directory.mkdir()
    (directory / "settings.json").write_text('{"region": "chosen-region"}')
    settings, store = load_settings(["--storage-dir", str(directory)])
    assert settings.region == "chosen-region" and store.directory == directory
    with pytest.raises(ValidationError):
        Settings(sync_batch_size=0, _env_file=None)


def test_atomic_settings_failure_keeps_previous_json(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path, legacy_path=tmp_path / "absent")
    store.write('{"region": "old"}')

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        store.write('{"region": "new"}')
    assert json.loads(store.path.read_text()) == {"region": "old"}
    assert list(tmp_path.iterdir()) == [store.path]


def test_invalid_legacy_settings_are_not_migrated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"sync_batch_size": 0}')
    store = SettingsStore(tmp_path / "new", legacy_path=legacy)
    with pytest.raises(ValidationError):
        load_settings([], store=store)
    assert not store.path.exists()
    assert legacy.exists()


@pytest.mark.parametrize(
    "platform, environment, ending",
    [
        ("darwin", {}, ("Library", "Application Support", "fz-manager-plus")),
        ("linux", {"XDG_CONFIG_HOME": "/example/config"}, ("example", "config", "fz-manager-plus")),
        ("win32", {"LOCALAPPDATA": "/example/local"}, ("example", "local", "fz-manager-plus")),
    ],
)
def test_platform_config_location(platform, environment, ending, monkeypatch):
    monkeypatch.setattr(sys, "platform", platform)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert config_directory().parts[-len(ending) :] == ending


def test_import_has_no_cli_or_http_side_effects():
    code = """
import sys
from unittest.mock import patch
sys.argv = ["embedded", "--not-a-fzmp-option"]
with patch("httpx.AsyncClient", side_effect=AssertionError("import created HTTP client")):
    import fz_manager_plus.cli
    import fz_manager_plus.runtime
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_archive_keeps_user_info_and_uses_relative_members(tmp_path):
    source = tmp_path / "mod-settings.dat"
    source.write_bytes(b"settings")
    info = tmp_path / "info.json"
    info.write_text("user-owned contents")
    result = Path(create_mod_settings_zip(str(tmp_path)))
    assert info.read_text() == "user-owned contents"
    with zipfile.ZipFile(result) as archive:
        assert set(archive.namelist()) == {"mod-settings.dat", "info.json"}
        assert archive.read("mod-settings.dat") == b"settings"
        assert json.loads(archive.read("info.json"))["name"] == "mod-settings.dat"


def test_archive_failure_preserves_existing_zip(tmp_path, monkeypatch):
    (tmp_path / "mod-settings.dat").write_bytes(b"settings")
    target = tmp_path / "mod-settings.zip"
    target.write_bytes(b"old archive")

    def fail(*args, **kwargs):
        raise OSError("disk error")

    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail)
    with pytest.raises(OSError):
        create_mod_settings_zip(str(tmp_path))
    assert target.read_bytes() == b"old archive"
    assert not list(tmp_path.glob(".mod-settings-*"))


def test_duplicate_archive_names_are_reported(tmp_path):
    for folder in ("one", "two"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "mod.zip").write_bytes(b"data")
    with pytest.raises(ValueError, match="Duplicate archive name"):
        find_by_extension(str(tmp_path), ".zip")
