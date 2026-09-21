import json
import zipfile
from os import path, walk
from pathlib import Path


def mod_archive_identity(archive_path: str) -> str | None:
    """The "{title} {version}" string factorio.zone reports as a mod's `text`,
    read from the archive's own info.json (Factorio requires the layout
    "<mod>_<version>/info.json"). Returns None if it can't be determined,
    e.g. a non-Factorio zip or an unexpected/missing info.json."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            info_names = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith("/info.json")
            ]
            if len(info_names) != 1:
                return None
            with archive.open(info_names[0]) as info_file:
                info = json.load(info_file)
        return f"{info['title']} {info['version']}"
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile):
        return None


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
