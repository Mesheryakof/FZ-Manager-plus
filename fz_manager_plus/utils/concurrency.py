from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


async def run_batched(jobs: list[Callable[[], Coroutine[Any, Any, None]]], batch_size: int) -> None:
    """Run `jobs` concurrently, at most `batch_size` in flight at once."""
    semaphore = asyncio.Semaphore(max(1, batch_size))

    async def run(job: Callable[[], Coroutine[Any, Any, None]]) -> None:
        async with semaphore:
            await job()

    await asyncio.gather(*(run(job) for job in jobs))
