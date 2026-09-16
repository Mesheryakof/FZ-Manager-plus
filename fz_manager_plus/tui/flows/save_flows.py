from __future__ import annotations

import re
from os import path

from textual_fspicker import SelectDirectory

from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost
from fz_manager_plus.tui.progress import progress_logger
from fz_manager_plus.utils.files import start_dir


class SaveFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    async def download(self, slot: str) -> None:
        session, settings = self.host.session, self.host.settings
        slot_index = int(slot.removeprefix("slot"))
        description = session.saves.get(slot, "")
        if description.endswith("(empty)"):
            self.host.push_log(Term.error("[download save]", f"Slot {slot_index} is empty"))
            return

        selected = await self.host.push_screen_wait(
            SelectDirectory(
                location=start_dir(settings.saves_path),
                title="Select download directory",
            )
        )
        if selected is None:
            return
        directory = str(selected)
        settings.saves_path = directory

        size_match = re.search(r"(\d+\.\d+)MB", description)
        expected_size = float(size_match[1]) * 1048576 if size_match else None
        target = path.join(directory, f"slot{slot_index}.zip")
        self.host.push_log(Term.info("[download save]", f"Downloading slot {slot_index}..."))
        try:
            await session.download_save_slot(
                slot,
                target,
                progress_logger(self.host.push_log, f"[download save] slot {slot_index}", expected_size),
            )
            self.host.push_log(Term.info("[download save]", f"Slot {slot_index}: done"))
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[download save]", str(ex)))

    async def delete(self, slot: str) -> None:
        session = self.host.session
        slot_index = int(slot.removeprefix("slot"))
        description = session.saves.get(slot, "")
        if description.endswith("(empty)"):
            self.host.push_log(Term.error("[delete save]", f"Slot {slot_index} is already empty"))
            return
        confirmed = await self.host.push_screen_wait(
            ConfirmScreen(f"Delete slot {slot_index} ({description})?")
        )
        if not confirmed:
            return
        try:
            await session.delete_save_slot(slot)
            self.host.push_log(Term.info("[delete save]", f"Deleted slot {slot_index}"))
        except Exception as ex:  # noqa: BLE001
            self.host.push_log(Term.error("[delete save]", str(ex)))
