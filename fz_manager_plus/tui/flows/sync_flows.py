from textual_fspicker import SelectDirectory

from fz_manager_plus.application.transfers import ModTransferService
from fz_manager_plus.domain.state import Mod, UploadItem
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ConfirmScreen, ModsUploadScreen
from fz_manager_plus.tui.flows.host import FlowHost
from fz_manager_plus.utils.files import start_dir


class SyncFlows:
    def __init__(self, host: FlowHost) -> None:
        self.host = host
        self.transfers = ModTransferService(host.session)

    async def run(self) -> None:
        self.host.session.require_ready("mods")
        settings = self.host.settings
        directory = await self.host.push_screen_wait(
            SelectDirectory(location=start_dir(settings.mods_path), title="Select mods folder")
        )
        if directory is None:
            return
        settings.mods_path = str(directory)
        await self.host.save_settings()
        plan = await self.transfers.prepare(str(directory))
        if not plan.upload and not plan.remove:
            self.host.push_log(Term.info("[sync]", "Nothing to sync -- server already matches."))
            return

        if plan.upload:
            await self._upload(plan.upload)
        if plan.remove:
            await self._remove(plan.remove)

    async def _upload(self, items: list[UploadItem]) -> None:
        async def run_uploads(notify):
            return await self.transfers.upload(items, notify)

        result = await self.host.push_screen_wait(
            ModsUploadScreen(f"Push {len(items)} mod(s) to the server?", items, run_uploads)
        )
        if result is None:
            self.host.push_log(Term.warn("[sync]", "Mod upload cancelled."))
        elif result:
            self.host.push_log(
                Term.error("[sync]", f"{len(result)} mod(s) failed: {', '.join(result)}")
            )
        else:
            self.host.push_log(Term.info("[sync]", f"Uploaded {len(items)} mod(s)."))

    async def _remove(self, mods: list[Mod]) -> None:
        names = ", ".join(mod.text for mod in mods)
        prompt = f"Delete {len(mods)} mod(s) from the server not in this folder? ({names})"
        if not await self.host.push_screen_wait(ConfirmScreen(prompt)):
            self.host.push_log(Term.warn("[sync]", "Server-side cleanup skipped."))
            return
        await self.host.session.delete_mods({mod.id for mod in mods})
        self.host.push_log(Term.info("[sync]", f"Deleted {len(mods)} mod(s) from the server."))
