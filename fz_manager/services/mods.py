import json
import os
import zipfile
from collections.abc import Callable
from os import path, walk

from fz_manager.api.client import FZClient
from fz_manager.api.models import Mod

MOD_SETTINGS_DAT = "mod-settings.dat"


class ModsService:
    """Business logic for mod-related operations (upload/enable/disable/delete)."""

    def __init__(self, client: FZClient):
        self.client = client

    @staticmethod
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
                    "description": "Mod settings for factorio.zone created with FZ-Manager tool by @michelsciortino",
                },
                fp,
            )

        zf = zipfile.ZipFile(mod_settings_zip_path, "w")
        zf.write(mod_settings_dat_path)
        zf.write(info_json_path)
        zf.close()
        os.remove(info_json_path)
        return mod_settings_zip_path

    @staticmethod
    def list_zip_files(mods_folder_path: str) -> tuple[str, list[str]]:
        root, _, filenames = next(walk(mods_folder_path), (None, None, []))
        return root, list(filter(lambda n: n.endswith(".zip"), filenames))

    @staticmethod
    def build_mods(root: str, filenames: list[str]) -> list[Mod]:
        mods: list[Mod] = []
        for name in filenames:
            file_path = path.join(root, name)
            size = path.getsize(file_path)
            mods.append(Mod(name, file_path, size))
        return mods

    async def upload_mod(self, mod: Mod, cb: Callable = None):
        await self.client.upload_mod(mod, cb)

    async def toggle_mod(self, mod_id: int, enabled: bool):
        await self.client.toggle_mod(mod_id, enabled)

    async def delete_mod(self, mod_id: int):
        await self.client.delete_mod(mod_id)
