import asyncio
from collections.abc import Awaitable, Callable


async def run_batched(jobs: list[Callable[[], Awaitable[None]]], batch_size: int) -> None:
    """Bound both active jobs and task count; cancellation joins every worker."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    pending = iter(jobs)

    async def consume() -> None:
        for job in pending:
            await job()

    async with asyncio.TaskGroup() as group:
        for _ in range(min(batch_size, len(jobs))):
            group.create_task(consume())
