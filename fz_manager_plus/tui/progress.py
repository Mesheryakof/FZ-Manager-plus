from __future__ import annotations

from collections.abc import Callable

from textual.widgets import ProgressBar

from fz_manager_plus.terminal import Term


class TransferProgress:
    """Aggregates byte-level progress from several concurrent transfers
    (mod/save uploads or downloads) into a single shared ProgressBar."""

    def __init__(self, bar: ProgressBar, total: float) -> None:
        self._bar = bar
        bar.update(total=total or None, progress=0)
        bar.display = True

    def tracker(self, known_size: float) -> Callable[[int], None]:
        """A progress callback for one transfer of `known_size` bytes (0 if
        unknown -- e.g. a save's size is only a parsed-from-text estimate).
        Unknown sizes grow the bar's total as bytes actually arrive, instead
        of leaving it stuck below 100%."""
        reported = 0

        def on_progress(bytes_done: int) -> None:
            nonlocal reported
            delta = bytes_done - reported
            reported = bytes_done
            if not known_size and self._bar.total is not None:
                self._bar.update(total=self._bar.total + delta)
            self._bar.advance(delta)

        return on_progress

    def finish(self) -> None:
        self._bar.display = False


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
