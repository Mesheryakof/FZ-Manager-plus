import asyncio
import json
import zipfile

import pytest

from fz_manager_plus.application.transfers import ModTransferService
from fz_manager_plus.domain.messages import ModEntry, ModsMessage
from fz_manager_plus.domain.state import TransferProgress, TransferResult
from fz_manager_plus.utils.concurrency import run_batched
from tests.fakes import eventually, ready_session


def _write_mod_zip(path, mod_name: str, title: str, version: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{mod_name}/info.json",
            json.dumps({"name": mod_name, "title": title, "version": version}),
        )


def test_prepare_skips_existing_and_flags_orphaned_remote_mods(tmp_path):
    async def check():
        session, _, _ = await ready_session()
        await session.handle_message(
            ModsMessage(
                type="mods",
                mods=[
                    ModEntry(id=1, text="existing.zip", enabled=True),
                    ModEntry(id=2, text="orphaned.zip", enabled=True),
                ],
            )
        )
        (tmp_path / "existing.zip").write_bytes(b"zip")
        (tmp_path / "new.zip").write_bytes(b"zip")
        plan = await ModTransferService(session).prepare(str(tmp_path))
        assert [item.label for item in plan.upload] == ["new.zip"]
        assert [mod.text for mod in plan.remove] == ["orphaned.zip"]
        await session.aclose()

    asyncio.run(check())


def test_prepare_flags_duplicate_remote_copies_keeping_one(tmp_path):
    async def check():
        session, _, _ = await ready_session()
        await session.handle_message(
            ModsMessage(
                type="mods",
                mods=[
                    ModEntry(id=1, text="existing.zip", enabled=True),
                    ModEntry(id=2, text="existing.zip", enabled=True),
                    ModEntry(id=3, text="existing.zip", enabled=True),
                ],
            )
        )
        (tmp_path / "existing.zip").write_bytes(b"zip")
        plan = await ModTransferService(session).prepare(str(tmp_path))
        assert plan.upload == []
        assert [mod.id for mod in plan.remove] == [2, 3]
        await session.aclose()

    asyncio.run(check())


def test_prepare_matches_by_archive_title_and_version_not_filename(tmp_path):
    async def check():
        session, _, _ = await ready_session()
        # The server reports "{title} {version}" (read from info.json server-side),
        # not the archive's OS filename -- a mismatch here used to cause every mod
        # to look "missing" and be re-uploaded on every sync.
        await session.handle_message(
            ModsMessage(
                type="mods",
                mods=[ModEntry(id=1, text="AAI Containers & Warehouses 0.4.0", enabled=True)],
            )
        )
        _write_mod_zip(
            tmp_path / "aai-containers-and-warehouses_0.4.0.zip",
            "aai-containers-and-warehouses",
            "AAI Containers & Warehouses",
            "0.4.0",
        )
        plan = await ModTransferService(session).prepare(str(tmp_path))
        assert plan.upload == []
        assert plan.remove == []
        await session.aclose()

    asyncio.run(check())


def test_batch_reports_partial_failure_and_bounds_concurrency(tmp_path):
    async def check():
        session, api, _ = await ready_session(sync_batch_size=2)
        for index in range(5):
            (tmp_path / f"{index}.zip").write_bytes(b"zip")
        transfers = ModTransferService(session)
        items = (await transfers.prepare(str(tmp_path))).upload
        active = peak = 0
        streams = []

        async def upload(name, stream, size, progress):
            nonlocal active, peak
            streams.append(stream)
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.005)
                if name == "2.zip":
                    raise ValueError("rejected")
                progress(size)
            finally:
                active -= 1

        api.hooks["upload_mod"] = upload
        events = []
        failures = await transfers.upload(items, events.append)
        assert failures == ["2.zip"]
        assert peak == 2 and active == 0
        assert all(stream.closed for stream in streams)
        assert len([event for event in events if isinstance(event, TransferResult)]) == 5
        assert len([event for event in events if isinstance(event, TransferProgress)]) == 4
        await session.aclose()

    asyncio.run(check())


def test_batch_cancellation_joins_jobs_and_closes_files(tmp_path):
    async def check():
        session, api, _ = await ready_session(sync_batch_size=2)
        for index in range(4):
            (tmp_path / f"{index}.zip").write_bytes(b"zip")
        transfers = ModTransferService(session)
        items = (await transfers.prepare(str(tmp_path))).upload
        streams = []

        async def upload(name, stream, size, progress):
            streams.append(stream)
            await asyncio.Event().wait()

        api.hooks["upload_mod"] = upload
        task = asyncio.create_task(transfers.upload(items, lambda event: None))
        await eventually(lambda: len(streams) == 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(streams) == 2 and all(stream.closed for stream in streams)
        assert not session._operations
        await session.aclose()

    asyncio.run(check())


def test_mod_mutations_wait_until_batch_finishes(tmp_path):
    async def check():
        session, api, _ = await ready_session()
        (tmp_path / "mod.zip").write_bytes(b"zip")
        service = ModTransferService(session)
        gate = asyncio.Event()

        async def upload(*args):
            await gate.wait()

        api.hooks["upload_mod"] = upload
        batch = asyncio.create_task(
            service.upload((await service.prepare(str(tmp_path))).upload, lambda event: None)
        )
        await eventually(lambda: any(name == "upload_mod" for name, _ in api.calls))
        delete = asyncio.create_task(session.delete_mod(1))
        await asyncio.sleep(0)
        assert not any(name == "delete_mod" for name, _ in api.calls)
        gate.set()
        await asyncio.gather(batch, delete)
        await session.aclose()

    asyncio.run(check())


def test_batch_worker_count_is_bounded():
    async def check():
        gate = asyncio.Event()
        started = 0

        async def job():
            nonlocal started
            started += 1
            await gate.wait()

        before = len(asyncio.all_tasks())
        task = asyncio.create_task(run_batched([job] * 1000, 3))
        await eventually(lambda: started == 3)
        assert len(asyncio.all_tasks()) <= before + 4
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
