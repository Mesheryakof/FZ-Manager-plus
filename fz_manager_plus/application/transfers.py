from collections.abc import Callable
from pathlib import Path

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.domain.state import (
    SyncPlan,
    TransferEvent,
    TransferProgress,
    TransferResult,
    UploadItem,
)
from fz_manager_plus.utils.async_io import blocking_io
from fz_manager_plus.utils.concurrency import run_batched
from fz_manager_plus.utils.files import find_by_extension, mod_archive_identity


class ModTransferService:
    def __init__(self, session: FactorioZoneSession):
        self.session = session

    async def prepare(self, directory: str) -> SyncPlan:
        """Diff local mod archives against remote mods. factorio.zone reports each
        mod as "{title} {version}" (from the archive's own info.json), not its
        filename, so that's what's read from each local archive and compared;
        archives whose identity can't be read fall back to their filename."""
        self.session.require_ready("mods")
        files = await blocking_io(find_by_extension, directory, ".zip")
        remote = {mod.text: mod for mod in self.session.mods}

        def inspect_files():
            identities = {name: mod_archive_identity(file) or name for name, file in files.items()}
            upload = [
                UploadItem(name, Path(file).stat().st_size, Path(file))
                for name, file in sorted(files.items())
                if identities[name] not in remote
            ]
            local_identities = set(identities.values())
            remove = [mod for key, mod in sorted(remote.items()) if key not in local_identities]
            return SyncPlan(upload, remove)

        return await blocking_io(inspect_files)

    async def upload(
        self, items: list[UploadItem], notify: Callable[[TransferEvent], None]
    ) -> list[str]:
        failed: list[str] = []
        async with self.session.mod_uploads() as upload:

            async def run_one(index: int) -> None:
                item = items[index]
                try:
                    self.session.require_ready("mods")
                    # Metadata open/close are short; all payload reads happen in the transport thread.
                    with item.path.open("rb") as stream:
                        await upload(
                            item.label,
                            stream,
                            item.size,
                            lambda done: notify(TransferProgress(index, done)),
                        )
                    notify(TransferResult(index))
                except Exception as error:
                    failed.append(item.label)
                    notify(TransferResult(index, str(error) or type(error).__name__))

            await run_batched(
                [lambda i=i: run_one(i) for i in range(len(items))],
                self.session.settings.sync_batch_size,
            )
        return failed
