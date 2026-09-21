import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def blocking_io(function: Callable[..., T], *args, **kwargs) -> T:
    """Finish in-flight file I/O before cancellation closes or removes its file."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        # Retrieve an I/O error as well, avoiding an unobserved task exception.
        task.result()
        raise
