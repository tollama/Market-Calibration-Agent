#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_PORT="${API_PORT:-8000}"
GUI_PORT="${GUI_PORT:-8501}"
DEMO_STATE_DIR="${DEMO_STATE_DIR:-$ROOT_DIR/.demo_state}"
API_PID_FILE="$DEMO_STATE_DIR/api.pid"
GUI_PID_FILE="$DEMO_STATE_DIR/gui.pid"

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

kill_by_port() {
  local port="$1"
  local label="$2"
  local pids

  if ! command -v lsof >/dev/null 2>&1; then
    warn "lsof not found; cannot stop ${label} by port ${port}"
    return 1
  fi

  pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN -n -P 2>/dev/null | tr '\n' ' ')"
  if [[ -z "${pids// /}" ]]; then
    return 1
  fi

  say "Stopping ${label} on port ${port}: ${pids}"
  # shellcheck disable=SC2086
  kill $pids >/dev/null 2>&1 || true
  return 0
}

stopped_any=0

if kill_pid_file "$API_PID_FILE" "API"; then
  stopped_any=1
fi
if kill_pid_file "$GUI_PID_FILE" "GUI launcher shell"; then
  stopped_any=1
fi

if kill_by_port "$API_PORT" "API"; then
  stopped_any=1
fi
if kill_by_port "$GUI_PORT" "GUI"; then
  stopped_any=1
fi

if [[ "$stopped_any" -eq 0 ]]; then
  say "No live demo processes found."
else
  say "Stop request sent."
fi
