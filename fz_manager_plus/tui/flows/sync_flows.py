from textual_fspicker import SelectDirectory

from fz_manager_plus.application.transfers import ModTransferService
from fz_manager_plus.terminal import Term
from fz_manager_plus.tui.components import ModsUploadScreen
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
        items = await self.transfers.prepare(str(directory))
        if not items:
            self.host.push_log(
                Term.info("[sync]", "Nothing to push -- server already has everything.")
            )
            return

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
