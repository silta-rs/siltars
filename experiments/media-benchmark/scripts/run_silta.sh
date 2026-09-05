#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$EXPERIMENT_DIR/../.." && pwd)"
export PYTHONPATH="$ROOT_DIR/python"

exec "$EXPERIMENT_DIR/.venv/bin/python" -m silta.cli dev \
  "$EXPERIMENT_DIR/silta_app.py:app" \
  --host 127.0.0.1 \
  --port "${SILTA_PORT:-8401}" \
  --runtime-bin "${SILTA_RUNTIME_BIN:-$ROOT_DIR/target/release/silta-runtime}"
