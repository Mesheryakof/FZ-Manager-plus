"""Local dev entry point for the Textual dashboard prototype.

Not wired into `pyproject.toml`'s `[tool.poetry.scripts]` on purpose - this
package is a standalone prototype and must not affect the `fzm`/`fz-manager`
console entry points, which keep pointing at `fz_manager.cli:main`.

Usage:

    poetry run python -m fz_manager.tui.run
"""

from fz_manager.tui.app import main

if __name__ == "__main__":
    main()
