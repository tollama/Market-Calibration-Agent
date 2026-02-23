#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
GUI_PORT="${GUI_PORT:-8501}"
HEALTH_PATH="${HEALTH_PATH:-/metrics}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-30}"
DEMO_STATE_DIR="${DEMO_STATE_DIR:-$ROOT_DIR/.demo_state}"
API_PID_FILE="$DEMO_STATE_DIR/api.pid"
GUI_PID_FILE="$DEMO_STATE_DIR/gui.pid"

_PLACEHOLDER_TOKENS=(
  ""
  "changemeplease"
  "your-token"
  "demo-token"
  "dev-token"
  "tsfm-dev-token"
  "example"
  "changeme"
  "placeholder"
)

is_placeholder_token() {
  local value="${1-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]' | xargs)"
  for p in "${_PLACEHOLDER_TOKENS[@]}"; do
    if [[ "$value" == "$p" ]]; then
      return 0
    fi
  done
  return 1
}

infer_tsfm_token() {
  TSFM_FORECAST_API_TOKEN="${TSFM_FORECAST_API_TOKEN:-${AUTH_TOKEN:-}}"
  if is_placeholder_token "$TSFM_FORECAST_API_TOKEN"; then
    DEMO_FORECAST_ENABLED=0
    warn "TSFM_FORECAST_API_TOKEN is not set to a real token (current: '${TSFM_FORECAST_API_TOKEN:-}')."
    warn "Set TSFM_FORECAST_API_TOKEN (or AUTH_TOKEN) to avoid /tsfm/forecast 401 errors during Run forecast."
    say "지금은 데모 모드, forecast 비활성"
  else
    DEMO_FORECAST_ENABLED=1
  fi
  export TSFM_FORECAST_API_TOKEN
  export AUTH_TOKEN="$TSFM_FORECAST_API_TOKEN"
  export DEMO_FORECAST_ENABLED
}
mkdir -p "$DEMO_STATE_DIR"

say() {
  printf '[live-demo] %s\n' "$*"
}

warn() {
  printf '[live-demo] WARNING: %s\n' "$*" >&2
}

require_cmd() {
  local cmd="$1"
  local install_hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command not found: $cmd ($install_hint)" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1
  else
    return 1
  fi
}

wait_for_api_health() {
  local url="$1"
  local timeout_sec="$2"
  local elapsed=0

  while (( elapsed < timeout_sec )); do
    if "$PYTHON_BIN" - "$url" >/dev/null 2>&1 <<'PY'
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=2) as response:
    sys.exit(0 if 200 <= response.status < 500 else 1)
PY
    then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  return 1
}

cleanup() {
  if [[ -f "$GUI_PID_FILE" ]]; then
    rm -f "$GUI_PID_FILE"
  fi

  if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    say "Stopping API (pid=$API_PID)"
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" 2>/dev/null || true
  fi
  rm -f "$API_PID_FILE"
}

trap cleanup EXIT INT TERM

say "Running preflight checks"
require_cmd "$PYTHON_BIN" "Install Python 3.11+ or set PYTHON_BIN"

py_version="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "Python 3.11+ is required (detected $py_version)." >&2
  exit 1
fi

say "Python: $($PYTHON_BIN --version 2>&1)"

if port_in_use "$API_PORT"; then
  warn "Port $API_PORT is already in use. Existing service may be reused or startup may fail."
fi
if port_in_use "$GUI_PORT"; then
  warn "Port $GUI_PORT is already in use. Streamlit startup may fail."
fi

say "Ensuring runtime dependencies are available from package extras"
if ! "$PYTHON_BIN" -m pip install -q -e ".[server,demo]"; then
  warn "Editable install failed (flat-layout detected or package metadata error)."
  warn "Falling back to source-tree import mode via PYTHONPATH."
  export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:$PYTHONPATH}"
fi

infer_tsfm_token

say "Starting API on http://${API_HOST}:${API_PORT}"
"$PYTHON_BIN" -m uvicorn api.app:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!
printf '%s\n' "$API_PID" > "$API_PID_FILE"

api_health_url="http://${API_HOST}:${API_PORT}${HEALTH_PATH}"
say "Waiting for API health: ${api_health_url} (timeout ${HEALTH_TIMEOUT_SEC}s)"
if ! wait_for_api_health "$api_health_url" "$HEALTH_TIMEOUT_SEC"; then
  echo "API did not become healthy within ${HEALTH_TIMEOUT_SEC}s. Check logs and port usage." >&2
  exit 1
fi
say "API is healthy"

export LIVE_DEMO_API_BASE="http://${API_HOST}:${API_PORT}"

say "Launching Streamlit GUI on http://127.0.0.1:${GUI_PORT}"
say "API endpoint: ${LIVE_DEMO_API_BASE}"
say "Tip: Use ./scripts/stop_live_demo.sh in another terminal to stop background processes"
printf '%s\n' "$$" > "$GUI_PID_FILE"

"$PYTHON_BIN" -m streamlit run demo/live_demo_app.py --server.port "$GUI_PORT"
