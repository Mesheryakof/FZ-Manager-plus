#!/usr/bin/env bash
# Runs the project's lint/format pipeline in the order that avoids
# ruff/isort disagreeing with each other:
#   1. ruff check --fix  -- autofixes (may rewrite import statements)
#   2. isort              -- sorts/groups imports
#   3. ruff format         -- final formatting pass
#
# Usage:
#   scripts/lint.sh              # whole project (fz_manager/ + tests/)
#   scripts/lint.sh path/to/file.py [more_files...]   # just those files (used by PyCharm File Watcher)
#   scripts/lint.sh --check      # check-only, no writes, exits non-zero if anything would change (for CI)

set -euo pipefail

# GUI-launched PyCharm on macOS often has a slimmer PATH than a login shell,
# so make sure common poetry install locations are visible.
export PATH="$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--check" ]]; then
    poetry run ruff check fz_manager tests
    poetry run isort --check-only fz_manager tests
    poetry run ruff format --check fz_manager tests
    exit 0
fi

if [[ $# -gt 0 ]]; then
    targets=("$@")
else
    targets=(fz_manager tests)
fi

poetry run ruff check --fix "${targets[@]}"
poetry run isort "${targets[@]}"
poetry run ruff format "${targets[@]}"
