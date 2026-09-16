from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from os import path, walk

MOD_SETTINGS_DAT = "mod-settings.dat"


@dataclass
class ModFile:
    name: str
    file_path: str
    size: int


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
                    "Mod settings for factorio.zone created with FZ-Manager tool by @michelsciortino"
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


def list_zip_files(mods_folder_path: str) -> tuple[str | None, list[str]]:
    root, _, filenames = next(walk(mods_folder_path), (None, None, []))
    return root, sorted(f for f in filenames if f.endswith(".zip"))


def build_mod_files(root: str, filenames: list[str]) -> list[ModFile]:
    mod_files = []
    for name in filenames:
        file_path = path.join(root, name)
        mod_files.append(ModFile(name=name, file_path=file_path, size=path.getsize(file_path)))
    return mod_files
