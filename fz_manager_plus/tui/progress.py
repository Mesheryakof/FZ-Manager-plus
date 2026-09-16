from __future__ import annotations

from collections.abc import Callable

from fz_manager_plus.terminal import Term


def progress_logger(
    log: Callable[[str], None], label: str, total: float | None
) -> Callable[[int], None]:
    """A progress callback for a single transfer that logs a text line at
    each 25% milestone -- used where there's no shared ProgressBar to
    aggregate into (e.g. a one-off download from the saves panel)."""
    reported: set[int] = set()

    def on_progress(bytes_done: int) -> None:
        if not total:
            return
        step = min(100, int(bytes_done * 100 / total) // 25 * 25)
        if step and step not in reported:
            reported.add(step)
            log(Term.info(label, f"{step}%"))

    return on_progress
