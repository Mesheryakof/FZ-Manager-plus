# FZ-Manager Plus

Terminal UI for managing a Factorio server hosted by [Factorio Zone](https://factorio.zone/), based on [FZ-Manager](https://github.com/michelsciortino/FZ-Manager).

Requires Python 3.14 or newer.

## Installation and launch

```sh
pip install fz-manager-plus
fzmp
# Equivalent:
fz-manager-plus
```

Run `fzmp --help` to see settings and command-line options. Enter an existing Factorio Zone token, or submit an empty token to create a new account.

## Available in the TUI

- Start a server by choosing a region, version and save slot; stop a running server.
- Send console commands from the log pane.
- Upload missing ZIP mods from a folder, including nested folders, with per-file progress.
- Enable, disable or delete mods; delete all uploaded mods after confirmation.
- Download and delete remote save slots. Replacing an existing local archive requires confirmation.
- Quit with `Ctrl+Q`. Background operations are cancelled and network clients are closed.

Mod sync matches **filenames**, not archive contents. It uploads missing names; it does not delete remote mods or compare versions/checksums. Duplicate ZIP filenames in different local folders are reported as a conflict.

The upload dialog can be cancelled before upload starts. After starting, wait for the results or quit the application. The API still supports save uploads and the project includes a mod-settings archive utility; neither has a menu action in this TUI.

## Connection and operation status

WebSocket connections recover automatically with delays of 1, 2, 4, 8, 16, then 30 seconds. The session logs in with its current token and refreshes server state before enabling dependent actions. Authentication failures ask for a token again.

Console commands, deletions and transfers are **not replayed** on reconnect. A server may have accepted a request before the connection failed; inspect the refreshed state before repeating it.

Start succeeds only after a running state and server address arrive. Default synchronization/start/stop timeouts are 60/600/3600 seconds. Adjust them with `--sync-timeout`, `--start-timeout`, `--stop-timeout` or the corresponding `FZM_*` environment variables. `--sync-batch-size` defaults to 3.

The log pane and log deduplication history are limited to 10,000 entries each.

## Settings

Settings and the crash log are stored in:

| Platform | Default directory |
| --- | --- |
| macOS | `~/Library/Application Support/fz-manager-plus` |
| Linux | `$XDG_CONFIG_HOME/fz-manager-plus`, or `~/.config/fz-manager-plus` |
| Windows | `%LOCALAPPDATA%/fz-manager-plus` |

Use `--storage-dir` or `FZM_STORAGE_DIR` to override the directory. The settings file is `settings.json`; the crash log is `crash.log`.

On first use of a directory without settings, the previous temporary-directory `.fzmp/settings.json` is imported if present. Its source is retained. Settings are validated before migration and written atomically; tokens are saved as soon as authentication succeeds. On POSIX systems the new settings file has mode `0600`.

CLI options override environment variables; environment variables override `.env`; `.env` overrides stored settings. Existing option names, numeric save-slot preferences and `FZM_*` variables remain supported. Importing modules or assigning a settings field performs no persistence or CLI parsing.

## Development

```sh
uv sync --group dev
uv run pytest -q
uv run ruff check fz_manager_plus tests
uv run ruff format --check fz_manager_plus tests
```

Tests use fake transports and temporary directories; they do not call Factorio Zone.

The composition root is `fz_manager_plus/runtime.py`. `domain` defines state and messages, `application` owns session/transfer workflows, `infrastructure` implements transports and archive utilities, and `tui` contains Textual views and user interaction. Rich styling stays at the UI boundary in `terminal.py`.

## Screenshot
![](assets/img.png?raw=true "FactorioZone Manager Plus")
