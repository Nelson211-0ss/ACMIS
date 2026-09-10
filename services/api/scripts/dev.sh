#!/usr/bin/env bash
# Starts the API against the local compose stack. Creates the venv on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -e ".[dev]"
fi
exec ./.venv/bin/uvicorn acmis.main:app --reload --host 0.0.0.0 --port 8000
