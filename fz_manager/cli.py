"""Console entry point for `fzm`/`fz-manager` (see pyproject.toml's
`[tool.poetry.scripts]`).

Launches the Textual dashboard TUI (`fz_manager.tui.app`), which has now
reached feature parity with the old questionary/prompt_toolkit UI
(`fz_manager.ui.app.Main`, removed) -- Start/Stop server, Manage mods,
Manage saves, attach-to-server console, and persisted last-used values.

No `Term.cls()` before/after like the old entry point needed: Textual owns
the terminal's alternate screen buffer itself and restores it on exit.
"""

from fz_manager.tui.app import main as run_tui


def main() -> None:
    run_tui()
