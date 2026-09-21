# FZ-Manager Plus

Terminal UI for managing a Factorio server hosted by [Factorio Zone](https://factorio.zone/), based on [FZ-Manager](https://github.com/michelsciortino/FZ-Manager).

Requires Python 3.11 or newer.

## Installation and launch

```sh
pip install fz-manager-plus
fzmp
# Equivalent:
fz-manager-plus
```

Or, without touching any existing Python environment:

```sh
uv tool install fz-manager-plus
```

Run `fzmp --help` to see settings and command-line options. Enter an existing Factorio Zone token, or submit an empty token to create a new account.

## Available in the TUI

- Start a server by choosing a region, version and save slot; stop a running server.
- Click the server address in the status bar to launch Steam and join it directly (requires Steam and Factorio to be installed).
- Send console commands from the log pane.
- Upload missing ZIP mods from a folder, including nested folders, with per-file progress.
- Hover a mod to reveal Enable/Disable and Delete buttons, also bound to `t`/`del` (shown in the footer); delete all uploaded mods after confirmation.
- Hover a save slot to reveal Download, Upload and Delete buttons, also bound to `d`/`u`/`del` (shown in the footer). Upload picks a local `.zip` and replaces the slot's content (confirmation required if it already holds a save); download requires confirmation to replace an existing local archive.
- Quit with `Ctrl+Q`. Background operations are cancelled and network clients are closed.

Mod sync matches on each archive's own `info.json` (`"{title} {version}"`, the same identity factorio.zone reports), not the local filename -- a mod discovered under an unrelated OS filename (e.g. from Steam Workshop) is still recognized as already uploaded. Archives whose identity can't be read fall back to filename matching. It uploads mods missing on the server, and, after asking for confirmation, deletes remote mods that are missing locally or are duplicate remote copies of the same identity (keeping one). Duplicate ZIP filenames in different local folders are reported as a conflict.

The upload dialog can be cancelled before upload starts. After starting, wait for the results or quit the application. The project includes a mod-settings archive utility with no menu action in this TUI.

## Connection and operation status

WebSocket connections recover automatically with delays of 1, 2, 4, 8, 16, then 30 seconds. The session logs in with its current token and refreshes server state before enabling dependent actions. Authentication failures ask for a token again.

Console commands, deletions and transfers are **not replayed** on reconnect. A server may have accepted a request before the connection failed; inspect the refreshed state before repeating it.

Start succeeds only after a running state and server address arrive. Default synchronization/start/stop timeouts are 60/600/3600 seconds. Adjust them with `--sync-timeout`, `--start-timeout`, `--stop-timeout` or the corresponding `FZM_*` environment variables. `--sync-batch-size` defaults to 3.

The log pane and log deduplication history are limited to 10,000 entries each.

## Settings

Settings, the crash log and the server log are stored in:

| Platform | Default directory |
| --- | --- |
| macOS | `~/Library/Application Support/fz-manager-plus` |
| Linux | `$XDG_CONFIG_HOME/fz-manager-plus`, or `~/.config/fz-manager-plus` |
| Windows | `%LOCALAPPDATA%/fz-manager-plus` |

Use `--storage-dir` or `FZM_STORAGE_DIR` to override the directory. The settings file is `settings.json`; the crash log is `crash.log`; everything shown in the log pane (connection status, console output, mod/save actions) is also timestamped and appended to `server.log`.

On first use of a directory without settings, the previous temporary-directory `.fzmp/settings.json` is imported if present. Its source is retained. Settings are validated before migration and written atomically; tokens are saved as soon as authentication succeeds. On POSIX systems the new settings file has mode `0600`.

CLI options override environment variables; environment variables override `.env`; `.env` overrides stored settings. Existing option names, numeric save-slot preferences and `FZM_*` variables remain supported. Importing modules or assigning a settings field performs no persistence or CLI parsing.

## Development

```sh
uv sync --group dev
```

### Checkers

Each command only reports; none of them rewrite files. Run before pushing — this is the same set of checks GitHub Actions runs on a pull request, so a green run locally means a green PR:

```sh
uv run ruff check source tests
uv run ruff format --check source tests
uv run isort --check-only source tests
uv run pytest -q
```

Tests use fake transports and temporary directories; they do not call Factorio Zone.

The package lives under `source/fz_manager_plus` so additional libraries can be developed alongside it inside `source/`. The composition root is `source/fz_manager_plus/runtime.py`. `domain` defines state and messages, `application` owns session/transfer workflows, `infrastructure` implements transports and archive utilities, and `tui` contains Textual views and user interaction. Rich styling stays at the UI boundary in `terminal.py`.

### CI

`.github/workflows/ci.yml` runs `lint`, `format` and `test` as separate jobs on every pull request targeting `main`. `test` runs against a matrix of Python 3.11, 3.12, 3.13 and 3.14 (the supported range). Every job fails the check instead of auto-fixing, and `uv sync --group dev --locked` also fails the job if `uv.lock` is out of date.

### Releasing a new version

Versions are bumped, committed and tagged in one step with [Commitizen](https://commitizen-tools.github.io/commitizen/), configured under `[tool.commitizen]` in `pyproject.toml` to use uv's own version provider (updates `pyproject.toml` *and* `uv.lock`) and the existing `v$version` tag format:

```sh
uv run cz bump
```

Useful flags (combine as needed):

| Flag | Effect |
| --- | --- |
| `--dry-run` | Preview the next version, tag and changelog entry; changes nothing |
| `--increment {MAJOR,MINOR,PATCH}` | Force a specific increment instead of inferring it from commits |
| `--devrelease N` / `-d N` | Dev/pre-release build, e.g. `0.1.2` -> `0.1.3.dev N` |
| `--prerelease {alpha,beta,rc}` / `-pr` | Pre-release build, e.g. `0.1.2` -> `0.1.3rc1` |
| `--changelog` / `-ch` | Regenerate `CHANGELOG.md` even if the version doesn't change |
| `--check-consistency` / `-cc` | Verify `pyproject.toml`/`uv.lock`/tag versions agree before bumping |
| `--annotated-tag` | Create an annotated (instead of lightweight) git tag |
| `--no-verify` | Skip local git commit hooks for the release commit |

This updates `pyproject.toml`, `uv.lock` and `CHANGELOG.md`, then creates the release commit and the `vX.Y.Z` tag. Push both to trigger a release:

```sh
git push origin main --tags
```

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which builds the sdist/wheel with `uv build`, verifies the tag matches `pyproject.toml`, and publishes to PyPI with `uv publish` using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no stored token). `dev` pre-releases go through the same workflow; PyPI treats them as pre-releases, installable with `pip install --pre`.

One-time setup: create a `pypi` environment in the repository's GitHub settings, and register this repository/workflow/environment as a Trusted Publisher for `fz-manager-plus` on PyPI.


## Screenshot
![](assets/img.png?raw=true "FactorioZone Manager Plus")