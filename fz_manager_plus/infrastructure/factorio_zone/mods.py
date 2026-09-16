from __future__ import annotations

import json
import os
import zipfile
from os import path

from fz_manager_plus.utils.files import find_by_extension

MOD_SETTINGS_DAT = "mod-settings.dat"


def create_mod_settings_zip(mods_folder_path: str) -> str:
    mod_settings_dat_path = path.join(mods_folder_path, MOD_SETTINGS_DAT)
    info_json_path = path.join(mods_folder_path, "info.json")
    mod_settings_zip_path = path.join(mods_folder_path, "mod-settings.zip")

    if not path.exists(mod_settings_dat_path):
        raise FileNotFoundError(f"Unable to find {MOD_SETTINGS_DAT}")

    with open(info_json_path, "w") as fp:
        json.dump(
            {
                "name": MOD_SETTINGS_DAT,
                "version": "0.1.0",
                "title": MOD_SETTINGS_DAT,
                "description": (
                    "Mod settings for factorio.zone created with FZ-Manager Plus tool by @mesheryakof"
                ),
            },
            fp,
        )

    try:
        with zipfile.ZipFile(mod_settings_zip_path, "w") as zf:
            zf.write(mod_settings_dat_path)
            zf.write(info_json_path)
    finally:
        os.remove(info_json_path)
    return mod_settings_zip_path


def list_zip_files(mods_folder_path: str) -> dict[str, str]:
    """Mod archive filename -> its absolute path, searched recursively.

    The Steam release nests each mod's zip inside its own per-version
    subfolder (mods/some-mod_1.2.3/some-mod_1.2.3.zip) instead of keeping
    the mods folder flat, so a single-level listing misses them.
    """
    return find_by_extension(mods_folder_path, ".zip")
