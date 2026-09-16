from __future__ import annotations

from os import path, walk


def find_by_extension(folder: str, extension: str) -> dict[str, str]:
    """Filename -> absolute path, recursively, for files ending in `extension`."""
    found: dict[str, str] = {}
    for root, _dirs, filenames in walk(folder):
        for name in filenames:
            if name.endswith(extension):
                found.setdefault(name, path.join(root, name))
    return found


def start_dir(remembered: str | None) -> str:
    """Best starting directory for a file/folder picker given a remembered
    setting -- which may itself be a directory, a file inside one (e.g. the
    save previously uploaded), or unset."""
    if not remembered:
        return "."
    if path.isdir(remembered):
        return remembered
    parent = path.dirname(remembered)
    return parent if parent and path.isdir(parent) else "."
