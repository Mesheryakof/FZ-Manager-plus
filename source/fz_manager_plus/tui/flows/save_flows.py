import re
from pathlib import Path

from textual_fspicker import FileOpen, Filters, SelectDirectory

from fz_manager_plus.domain.errors import OperationError
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ConfirmScreen
from fz_manager_plus.tui.flows.host import FlowHost
from fz_manager_plus.tui.progress import progress_logger
from fz_manager_plus.utils.files import start_dir

ZIP_FILTERS = Filters(("Zip archives", lambda path: path.suffix.lower() == ".zip"))


class SaveFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host

    def _description(self, slot: str) -> str:
        self.host.session.require_ready("saves")
        description = self.host.session.saves.get(slot)
        if not description or description.endswith("(empty)"):
            raise OperationError("Save slot is empty or unknown")
        return description

    async def download(self, slot: str) -> None:
        description = self._description(slot)
        settings = self.host.settings
        selected = await self.host.push_screen_wait(
            SelectDirectory(
                location=start_dir(settings.saves_path),
                title="Select download directory",
            )
        )
        if selected is None:
            return
        settings.saves_path = str(selected)
        await self.host.save_settings()
        target = Path(selected) / f"{slot}.zip"
        if target.exists() and not await self.host.push_screen_wait(
            ConfirmScreen(f"Replace existing archive '{target.name}'?")
        ):
            return
        size_match = re.search(r"(\d+(?:\.\d+)?)\s*MB", description)
        expected_size = float(size_match[1]) * 1048576 if size_match else None
        self.host.push_log(Term.info("[download save]", f"Downloading {slot}..."))
        await self.host.session.download_save_slot(
            slot,
            str(target),
            progress_logger(self.host.push_log, f"[download save] {slot}", expected_size),
        )
        self.host.push_log(Term.info("[download save]", f"{slot}: done"))

    async def delete(self, slot: str) -> None:
        description = self._description(slot)
        if await self.host.push_screen_wait(ConfirmScreen(f"Delete {slot} ({description})?")):
            await self.host.session.delete_save_slot(slot)
            self.host.push_log(Term.info("[delete save]", f"Deleted {slot}"))

    async def upload(self, slot: str) -> None:
        self.host.session.require_ready("saves")
        description = self.host.session.saves.get(slot)
        if description is None:
            raise OperationError("Unknown save slot")
        settings = self.host.settings
        selected = await self.host.push_screen_wait(
            FileOpen(
                location=start_dir(settings.saves_path),
                title="Select save archive to upload",
                filters=ZIP_FILTERS,
            )
        )
        if selected is None:
            return
        settings.saves_path = str(Path(selected).parent)
        await self.host.save_settings()
        used = bool(description) and not description.endswith("(empty)")
        if used and not await self.host.push_screen_wait(
            ConfirmScreen(f"Replace existing save in {slot} ({description})?")
        ):
            return
        path = Path(selected)
        size = path.stat().st_size
        self.host.push_log(Term.info("[upload save]", f"Uploading {path.name} to {slot}..."))
        with path.open("rb") as stream:
            await self.host.session.upload_save(
                path.name,
                stream,
                size,
                slot,
                progress_logger(self.host.push_log, f"[upload save] {slot}", size),
            )
        self.host.push_log(Term.info("[upload save]", f"{slot}: done"))
