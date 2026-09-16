from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from textual.widgets import Static


class VersionLabel(Static):
    DEFAULT_CSS = """
    VersionLabel {
        width: auto;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        try:
            text = f"v{version('fz-manager-plus')}"
        except PackageNotFoundError:
            text = "v?"
        super().__init__(text, **kwargs)
