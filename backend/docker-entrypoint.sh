#!/bin/sh
# Container entrypoint.
#
# PaaS providers (Render, Fly, Cloud Run) mount a volume that is owned by root,
# and the container usually runs as a non-root user, so the SQLite database and
# uploads would fail to open. Make the data directory writable first, then drop
# privileges and hand the process over to uvicorn.
set -eu

DATA_DIR="${DATA_DIR:-/app/data}"
PORT="${PORT:-8000}"
export DATA_DIR PORT

mkdir -p "$DATA_DIR"

if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser "$DATA_DIR"
  exec su -s /bin/sh appuser -c "exec uvicorn main:app --host 0.0.0.0 --port $PORT"
fi

exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
