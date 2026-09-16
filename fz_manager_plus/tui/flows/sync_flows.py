from __future__ import annotations

import re
from functools import partial
from os import path

from textual_fspicker import SelectDirectory

from fz_manager_plus.infrastructure.factorio_zone import mods as mods_fs
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ChoiceScreen, ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost
from fz_manager_plus.utils.concurrency import run_batched
from fz_manager_plus.utils.files import find_matching, start_dir


def _local_save_files(folder: str) -> dict[str, str]:
    """slot name -> file path, for `slotN.zip` files directly inside
    `folder` -- the same naming SaveFlows.download() already writes,
    used here symmetrically for matching on push/pull."""
    return find_matching(folder, r"(slot\d+)\.zip")


class SyncFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def run(self) -> None:
        """Push local mods/saves to the server, or pull saves back down.

        Matching is by name only (mod filename <-> mod.text; save slot
        number <-> local `slotN.zip`), no content/size comparison -- and
        only ever fills gaps, never deletes or overwrites. Mods have no
        download endpoint (FactorioZoneAPI has upload_mod/toggle_mod/
        delete_mod, no download_mod), so pulling only ever applies to
        saves; mods sync is push-only.
        """
        settings = self.host.settings
        picked_mods_dir = await self.host.push_screen_wait(
            SelectDirectory(location=start_dir(settings.mods_path), title="Select mods folder")
        )
        if picked_mods_dir is None:
            return
        mods_folder = str(picked_mods_dir)
        settings.mods_path = mods_folder

        picked_saves_dir = await self.host.push_screen_wait(
            SelectDirectory(location=start_dir(settings.saves_path), title="Select saves folder")
        )
        if picked_saves_dir is None:
            return
        saves_folder = str(picked_saves_dir)
        settings.saves_path = saves_folder

        direction = await self.host.push_screen_wait(
            ChoiceScreen(
                "Sync direction:",
                [
                    ("Push to server (local -> server)", "push"),
                    ("Pull from server (server -> local, saves only)", "pull"),
                ],
            )
        )
        if direction is None:
            return

        if direction == "push":
            await self._push(mods_folder, saves_folder)
        else:
            await self._pull(saves_folder)

    async def _push(self, mods_folder: str, saves_folder: str) -> None:
        session, settings = self.host.session, self.host.settings
        zip_files = mods_fs.list_zip_files(mods_folder)
        remote_mod_names = {m.text for m in session.mods}
        missing_mods = [name for name in zip_files if name not in remote_mod_names]

        local_saves = _local_save_files(saves_folder)
        missing_saves = {
            slot: file_path
            for slot, file_path in local_saves.items()
            if session.saves.get(slot, "").endswith("(empty)")
        }
        occupied_saves = [
            slot
            for slot in local_saves
            if slot not in missing_saves and not session.saves.get(slot, "").endswith("(empty)")
        ]

        if not missing_mods and not missing_saves:
            self.host.push_log(Term.info("[sync]", "Nothing to push -- server already has everything."))
            return

        confirmed = await self.host.push_screen_wait(
            ConfirmScreen(
                f"Push {len(missing_mods)} mod(s) and {len(missing_saves)} save(s) to the server?"
            )
        )
        if not confirmed:
            return

        mod_sizes = {name: path.getsize(zip_files[name]) for name in missing_mods}
        save_sizes = {slot: path.getsize(file_path) for slot, file_path in missing_saves.items()}
        progress = self.host.start_transfer_progress(sum(mod_sizes.values()) + sum(save_sizes.values()))

        async def upload_mod_job(name: str) -> None:
            self.host.push_log(Term.info("[sync]", f"Uploading mod {name}..."))
            try:
                with open(zip_files[name], "rb") as fh:
                    await session.upload_mod(name, fh, mod_sizes[name], progress.tracker(mod_sizes[name]))
                self.host.push_log(Term.info("[sync]", f"{name}: done"))
            except Exception as ex:  # noqa: BLE001
                self.host.push_log(Term.error("[sync]", f"{name}: {ex}"))

        async def upload_save_job(slot: str, file_path: str) -> None:
            filename = path.basename(file_path)
            self.host.push_log(Term.info("[sync]", f"Uploading save {filename} to {slot}..."))
            try:
                with open(file_path, "rb") as fh:
                    await session.upload_save(
                        filename, fh, save_sizes[slot], slot, progress.tracker(save_sizes[slot])
                    )
                self.host.push_log(Term.info("[sync]", f"{slot}: done"))
            except Exception as ex:  # noqa: BLE001
                self.host.push_log(Term.error("[sync]", f"{slot}: {ex}"))

        jobs = [partial(upload_mod_job, name) for name in missing_mods]
        jobs += [partial(upload_save_job, slot, file_path) for slot, file_path in missing_saves.items()]
        try:
            await run_batched(jobs, settings.sync_batch_size)
        finally:
            progress.finish()

        for slot in occupied_saves:
            self.host.push_log(
                Term.warn("[sync]", f"{slot} already has a save on the server -- skipped, not overwritten")
            )

    async def _pull(self, saves_folder: str) -> None:
        session, settings = self.host.session, self.host.settings
        self.host.push_log(
            Term.info("[sync]", "Mods have no download endpoint on the server -- skipping mods.")
        )

        local_saves = _local_save_files(saves_folder)
        missing_locally = {
            slot: description
            for slot, description in session.saves.items()
            if not description.endswith("(empty)") and slot not in local_saves
        }

        if not missing_locally:
            self.host.push_log(Term.info("[sync]", "Nothing to pull -- local folder already has everything."))
            return

        confirmed = await self.host.push_screen_wait(
            ConfirmScreen(f"Pull {len(missing_locally)} save(s) from the server?")
        )
        if not confirmed:
            return

        sizes: dict[str, float] = {}
        for slot, description in missing_locally.items():
            size_match = re.search(r"(\d+\.\d+)MB", description)
            sizes[slot] = float(size_match[1]) * 1048576 if size_match else 0

        progress = self.host.start_transfer_progress(sum(sizes.values()))

        async def download_job(slot: str) -> None:
            target = path.join(saves_folder, f"{slot}.zip")
            self.host.push_log(Term.info("[sync]", f"Downloading {slot}..."))
            try:
                await session.download_save_slot(slot, target, progress.tracker(sizes[slot]))
                self.host.push_log(Term.info("[sync]", f"{slot}: done"))
            except Exception as ex:  # noqa: BLE001
                self.host.push_log(Term.error("[sync]", f"{slot}: {ex}"))

        jobs = [partial(download_job, slot) for slot in missing_locally]
        try:
            await run_batched(jobs, settings.sync_batch_size)
        finally:
            progress.finish()
