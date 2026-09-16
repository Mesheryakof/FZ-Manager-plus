from collections.abc import Callable
from pathlib import Path

from fz_manager_plus.application.session import FactorioZoneSession
from fz_manager_plus.domain.state import TransferEvent, TransferProgress, TransferResult, UploadItem
from fz_manager_plus.utils.async_io import blocking_io
from fz_manager_plus.utils.concurrency import run_batched
from fz_manager_plus.utils.files import find_by_extension


class ModTransferService:
    def __init__(self, session: FactorioZoneSession):
        self.session = session

    async def prepare(self, directory: str) -> list[UploadItem]:
        self.session.require_ready("mods")
        files = await blocking_io(find_by_extension, directory, ".zip")
        names = {mod.text for mod in self.session.mods}

        def inspect_files():
            return [
                UploadItem(name, Path(file).stat().st_size, Path(file))
                for name, file in sorted(files.items())
                if name not in names
            ]

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
