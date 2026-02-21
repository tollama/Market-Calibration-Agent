#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3.11 is required. Set PYTHON_BIN if needed." >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install -q fastapi pydantic pandas numpy pyarrow httpx websockets pyyaml uvicorn streamlit

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"$PYTHON_BIN" -m uvicorn api.app:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!
sleep 2

export LIVE_DEMO_API_BASE="http://${API_HOST}:${API_PORT}"
"$PYTHON_BIN" -m streamlit run demo/live_demo_app.py --server.port 8501
