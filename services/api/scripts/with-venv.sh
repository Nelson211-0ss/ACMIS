#!/usr/bin/env bash
# Run a command inside the API's virtual environment, creating it on first use.
#
# Exists so `turbo run typecheck` works from a clean checkout without anyone
# having to remember to activate anything — a bare `mypy` resolves to whatever
# is on PATH, which in CI is nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Creating the API virtual environment (first run only)…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -e ".[dev]"
fi
exec ./.venv/bin/"$@"
