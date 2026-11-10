#!/usr/bin/env bash
# Start the Study Companion API in development mode.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if [ -d "../.venv" ]; then
  PYTHON="../.venv/bin/python"
elif [ -d "venv" ]; then
  PYTHON="venv/bin/python"
else
  PYTHON="python3"
fi

exec "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
