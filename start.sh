#!/usr/bin/env bash
# Start all Goldium services: Backend (8000), lm (8010), frontend (5173).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/Backend"
LM_DIR="$ROOT/lm"
FRONTEND_DIR="$ROOT/frontend"

BACKEND_PORT="${BACKEND_PORT:-8000}"
LM_PORT="${LM_PORT:-8010}"
FRONTEND_PORT="${PORT:-5173}"

PIDS=()

cleanup() {
  echo
  echo "Stopping services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "All services stopped."
  exit 0
}

trap cleanup SIGINT SIGTERM

ensure_backend_venv() {
  if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
    echo "Creating Backend venv..."
    python3 -m venv "$BACKEND_DIR/.venv"
    "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  fi
}

ensure_lm_venv() {
  if [[ ! -d "$LM_DIR/.venv" ]]; then
    echo "Creating lm venv..."
    python3 -m venv "$LM_DIR/.venv"
    "$LM_DIR/.venv/bin/pip" install -r "$LM_DIR/requirements.txt"
  fi
}

ensure_frontend_deps() {
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

ensure_postgres() {
  if python3 -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1',5432)); s.close()" 2>/dev/null; then
    return 0
  fi
  if command -v docker &>/dev/null && docker ps -a --format '{{.Names}}' | grep -qx goldium-postgres; then
    echo "Starting PostgreSQL (docker: goldium-postgres)..."
    docker start goldium-postgres >/dev/null
    for _ in $(seq 1 20); do
      if docker exec goldium-postgres pg_isready -q 2>/dev/null; then
        echo "PostgreSQL is ready."
        return 0
      fi
      sleep 1
    done
  fi
  echo "WARNING: PostgreSQL not reachable on localhost:5432 — Backend may fail to start."
  echo "         Start Postgres or run: docker start goldium-postgres"
}

start_backend() {
  echo "Starting Backend on http://127.0.0.1:${BACKEND_PORT}"
  (
    cd "$BACKEND_DIR"
    exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
  ) &
  PIDS+=($!)
}

wait_for_url() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 60); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "${label} is ready."
      return 0
    fi
    sleep 1
  done
  echo "WARNING: ${label} did not become ready in time."
  return 1
}

start_lm() {
  echo "Starting lm (Stock AI) on http://127.0.0.1:${LM_PORT}"
  (
    cd "$LM_DIR"
    exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port "$LM_PORT"
  ) &
  PIDS+=($!)
}

start_frontend() {
  echo "Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
  (
    cd "$FRONTEND_DIR"
    exec env PORT="$FRONTEND_PORT" BACKEND_PORT="$BACKEND_PORT" LM_PORT="$LM_PORT" npm run dev
  ) &
  PIDS+=($!)
}

ensure_backend_venv
ensure_lm_venv
ensure_frontend_deps
ensure_postgres

start_backend
wait_for_url "http://127.0.0.1:${BACKEND_PORT}/health" "Backend"

start_lm
start_frontend

echo
echo "All services running:"
echo "  Backend API:  http://127.0.0.1:${BACKEND_PORT}  (docs: /docs)"
echo "  Stock AI lm:  http://127.0.0.1:${LM_PORT}"
echo "  Frontend:     http://127.0.0.1:${FRONTEND_PORT}"
echo
echo "Press Ctrl+C to stop all services."

wait
