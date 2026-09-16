import json
import os
import tempfile
import zipfile
from pathlib import Path

from fz_manager_plus.utils.files import find_by_extension

MOD_SETTINGS_DAT = "mod-settings.dat"


def create_mod_settings_zip(mods_folder_path: str) -> str:
    """Create an archive without creating or modifying the user's info.json."""
    folder = Path(mods_folder_path)
    source = folder / MOD_SETTINGS_DAT
    if not source.is_file():
        raise FileNotFoundError(f"Unable to find {MOD_SETTINGS_DAT}")
    target = folder / "mod-settings.zip"
    fd, name = tempfile.mkstemp(prefix=".mod-settings-", suffix=".zip", dir=folder)
    os.close(fd)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(source, arcname=MOD_SETTINGS_DAT)
            archive.writestr(
                "info.json",
                json.dumps(
                    {
                        "name": MOD_SETTINGS_DAT,
                        "version": "0.1.0",
                        "title": MOD_SETTINGS_DAT,
                        "description": "Mod settings for factorio.zone created with FZ-Manager Plus",
                    }
                ),
            )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)


def list_zip_files(mods_folder_path: str) -> dict[str, str]:
    return find_by_extension(mods_folder_path, ".zip")
