#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_PORT="${API_PORT:-8000}"
GUI_PORT="${GUI_PORT:-8501}"
DEMO_STATE_DIR="${DEMO_STATE_DIR:-$ROOT_DIR/.demo_state}"
API_PID_FILE="$DEMO_STATE_DIR/api.pid"
GUI_PID_FILE="$DEMO_STATE_DIR/gui.pid"
PYTHON_BIN="${PYTHON_BIN:-python3}"

say() {
  printf '[live-demo-stop] %s\n' "$*"
}

warn() {
  printf '[live-demo-stop] WARNING: %s\n' "$*" >&2
}

kill_pid_file() {
  local file="$1"
  local name="$2"

  if [[ ! -f "$file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$file")"
  if [[ -z "$pid" ]]; then
    rm -f "$file"
    return 1
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    say "Stopping ${name} (pid=$pid)"
    kill "$pid" >/dev/null 2>&1 || true
  else
    warn "${name} pid file exists but process is not running (pid=$pid)"
  fi

  rm -f "$file"
  return 0
}

kill_by_pids() {
  local label="$1"
  local pids="$2"

  if [[ -z "${pids// /}" ]]; then
    return 1
  fi

  say "Stopping ${label} PIDs: ${pids}"
  # shellcheck disable=SC2086
  kill $pids >/dev/null 2>&1 || true
  return 0
}

kill_by_command() {
  local pattern="$1"
  local label="$2"
  local pids

  pids="$(ps -ef | grep -E "$pattern" | grep -v grep | awk '{print $2}' | sort -u)"
  if [[ -z "${pids// /}" ]]; then
    return 1
  fi

  kill_by_pids "$label" "$pids"
}

kill_by_port() {
  local port="$1"
  local label="$2"
  local pattern="$3"
  local pids

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null | tr '\n' ' ')"
    if [[ -n "${pids// /}" ]]; then
      say "Stopping ${label} on port ${port}: ${pids}"
      kill_by_pids "$label" "$pids"
      return 0
    fi
    return 1
  fi

  if [[ -n "$pattern" ]]; then
    warn "lsof not found; cannot strictly verify ${label} by port ${port}; trying process pattern fallback"
    kill_by_command "$pattern" "$label"
    return $?
  fi

  return 1
}

port_in_use() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1
    return $?
  fi

  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    warn "Python not found for fallback port check; assume port ${port} is still in use"
    return 0
  fi

  "$PYTHON_BIN" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.2)
    if sock.connect_ex(("127.0.0.1", port)) == 0:
        sys.exit(0)
sys.exit(1)
PY
}

wait_for_ports_free() {
  local max_retries=20
  local interval_sec=0.5

  for ((i = 1; i <= max_retries; i++)); do
    local api_in_use=0
    local gui_in_use=0

    if port_in_use "$API_PORT"; then
      api_in_use=1
    fi
    if port_in_use "$GUI_PORT"; then
      gui_in_use=1
    fi

    if ((api_in_use == 0 && gui_in_use == 0)); then
      say "Ports are free (api=${API_PORT}, gui=${GUI_PORT})."
      return 0
    fi

    if ((i < max_retries)); then
      sleep "$interval_sec"
    fi
  done

  warn "Ports still in use: api=${API_PORT}(in_use=$api_in_use), gui=${GUI_PORT}(in_use=$gui_in_use)"
  return 1
}

stopped_any=0

if kill_pid_file "$API_PID_FILE" "API"; then
  stopped_any=1
fi
if kill_pid_file "$GUI_PID_FILE" "GUI launcher"; then
  stopped_any=1
fi

if kill_by_port "$API_PORT" "API" "api\.app:app"; then
  stopped_any=1
fi
if kill_by_port "$GUI_PORT" "GUI" "streamlit run demo/live_demo_app\.py"; then
  stopped_any=1
fi

if [[ "$stopped_any" -eq 0 ]]; then
  say "No live demo processes found."
else
  say "Stop request sent."
fi

if ! wait_for_ports_free; then
  exit 1
fi
