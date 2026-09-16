from os import path, walk
from pathlib import Path


def find_by_extension(folder: str, extension: str) -> dict[str, str]:
    """Discover archives deterministically; ambiguous filenames are an error."""
    directory = Path(folder).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(folder)
    found: dict[str, str] = {}

    def fail(error: OSError) -> None:
        raise error

    for root, dirs, filenames in walk(directory, onerror=fail):
        dirs.sort()
        for name in sorted(filenames):
            if name.endswith(extension):
                candidate = str(Path(root) / name)
                if name in found:
                    raise ValueError(
                        f"Duplicate archive name '{name}': {found[name]} and {candidate}"
                    )
                found[name] = candidate
    return found


def start_dir(remembered: str | None) -> str:
    if not remembered:
        return "."
    if path.isdir(remembered):
        return remembered
    parent = path.dirname(remembered)
    return parent if parent and path.isdir(parent) else "."
