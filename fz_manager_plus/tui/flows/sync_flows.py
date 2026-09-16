from __future__ import annotations

from collections.abc import Awaitable, Callable
from os import path

from textual_fspicker import SelectDirectory

from fz_manager_plus.infrastructure.factorio_zone import mods as mods_fs
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ModsUploadScreen, UploadItem
from fz_manager_plus.tui.flows.host import FlowHost
from fz_manager_plus.utils.files import start_dir


class SyncFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def run(self) -> None:
        """Push local mods that aren't on the server yet.

        Matching is by filename only (mod filename <-> mod.text), no
        content/size comparison -- only ever fills gaps, never deletes or
        overwrites.
        """
        settings = self.host.settings
        picked_mods_dir = await self.host.push_screen_wait(
            SelectDirectory(location=start_dir(settings.mods_path), title="Select mods folder")
        )
        if picked_mods_dir is None:
            return
        mods_folder = str(picked_mods_dir)
        settings.mods_path = mods_folder

        session = self.host.session
        zip_files = mods_fs.list_zip_files(mods_folder)
        remote_mod_names = {m.text for m in session.mods}
        missing_mods = [name for name in zip_files if name not in remote_mod_names]

        if not missing_mods:
            self.host.push_log(Term.info("[sync]", "Nothing to push -- server already has everything."))
            return

        await self._push_mods(zip_files, missing_mods)

    async def _push_mods(self, zip_files: dict[str, str], missing_mods: list[str]) -> None:
        session, settings = self.host.session, self.host.settings
        mod_sizes = {name: path.getsize(zip_files[name]) for name in missing_mods}

        def build_upload(name: str) -> Callable[[Callable[[int], None]], Awaitable[None]]:
            async def upload(progress: Callable[[int], None]) -> None:
                with open(zip_files[name], "rb") as fh:
                    await session.upload_mod(name, fh, mod_sizes[name], progress)

            return upload

        items = [UploadItem(label=name, size=mod_sizes[name], upload=build_upload(name)) for name in missing_mods]
        result = await self.host.push_screen_wait(
            ModsUploadScreen(f"Push {len(items)} mod(s) to the server?", items, settings.sync_batch_size)
        )
        if result is None:
            self.host.push_log(Term.warn("[sync]", "Mod upload cancelled."))
        elif result:
            self.host.push_log(Term.error("[sync]", f"{len(result)} mod(s) failed: {', '.join(result)}"))
        else:
            self.host.push_log(Term.info("[sync]", f"Uploaded {len(items)} mod(s)."))
