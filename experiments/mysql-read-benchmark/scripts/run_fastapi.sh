#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$EXPERIMENT_DIR"

exec .venv/bin/python -m uvicorn fastapi_app:app \
  --host 127.0.0.1 \
  --port "${FASTAPI_PORT:-8302}" \
  --loop uvloop \
  --http httptools \
  --no-access-log
