#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# rollout_hardening_gate.sh
#
# Required inputs (environment variables):
# - PYTHON_BIN (default: python3.11)
# - API_HOST (default: 127.0.0.1)
# - API_PORT (default: 8100)
# - API_BASE (default: http://$API_HOST:$API_PORT)
# - TSFM_FORECAST_API_TOKEN (preferred) or AUTH_TOKEN: required non-placeholder token for auth
# - HEALTH_TIMEOUT_SEC (default: 45)
# - ROLLOUT_REPORT_DIR (default: artifacts/rollout_gate)
# - ROLLOUT_GATE_DRY_RUN (default: 0)
# - ROLLOUT_PERF_REQUESTS (default: 60)
# - ROLLOUT_PERF_UNIQUE (default: 12)
# - ROLLOUT_PERF_LATENCY_MS (default: 15)
# - ROLLOUT_PERF_P95_MS (default: 320)
# - ROLLOUT_PERF_CYCLE_S (default: 90)
# - MARKET_ID (default: mkt-smoke-001)
# - DERIVED_DIR (optional override for fixture working directory)
#
# Outputs/artifacts:
# - <ROLLOUT_REPORT_DIR>/rollout_hardening_gate_summary.json
# - <ROLLOUT_REPORT_DIR>/live_demo_smoke_report.md
# - <ROLLOUT_REPORT_DIR>/live_demo_security_report.md
# - <ROLLOUT_REPORT_DIR>/logs/live_demo_smoke.log
# - <ROLLOUT_REPORT_DIR>/logs/live_demo_security.log
# - <ROLLOUT_REPORT_DIR>/logs/runtime_metrics_smoke.log
# - <ROLLOUT_REPORT_DIR>/logs/perf_bench.log
# - <ROLLOUT_REPORT_DIR>/logs/perf_bench_result.json
# - <ROLLOUT_REPORT_DIR>/logs/openapi_smoke.log
# - <ROLLOUT_REPORT_DIR>/logs/openapi_smoke_report.json
# ---------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8100}"
API_BASE="${API_BASE:-http://$API_HOST:$API_PORT}"
AUTH_TOKEN="${TSFM_FORECAST_API_TOKEN:-${AUTH_TOKEN:-}}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-45}"
REPORT_DIR="${ROLLOUT_REPORT_DIR:-artifacts/rollout_gate}"
GATE_LOG_DIR="${REPORT_DIR}/logs"
DRY_RUN="${ROLLOUT_GATE_DRY_RUN:-0}"
PERF_REQUESTS="${ROLLOUT_PERF_REQUESTS:-60}"
PERF_UNIQUE="${ROLLOUT_PERF_UNIQUE:-12}"
PERF_LATENCY_MS="${ROLLOUT_PERF_LATENCY_MS:-15}"
PERF_P95_MS="${ROLLOUT_PERF_P95_MS:-320}"
PERF_CYCLE_S="${ROLLOUT_PERF_CYCLE_S:-90}"
MARKET_ID="${MARKET_ID:-mkt-smoke-001}"

is_placeholder_token() {
  local token
  token="${1,,}"
  token="${token// /}"
  case "$token" in
    ""|tsfm-dev-token|changeme|changemeplease|your-token|placeholder)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if is_placeholder_token "$AUTH_TOKEN"; then
  echo "Missing or placeholder TSFM_FORECAST_API_TOKEN/AUTH_TOKEN (current: '${AUTH_TOKEN}'). Set a real token before running this gate." >&2
  exit 1
fi

mkdir -p "$REPORT_DIR" "$GATE_LOG_DIR"

TMP_DIR="$(mktemp -d)"
DERIVED_DIR="${DERIVED_DIR:-$TMP_DIR/derived}"
mkdir -p "$DERIVED_DIR/metrics" "$DERIVED_DIR/alerts" "$DERIVED_DIR/reports/postmortem"

API_PID=""
OVERALL_STATUS="success"
START_EPOCH="$(date +%s)"
START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
STEP_ROWS=""

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] $*"
}

json_escape() {
  "${PYTHON_BIN}" -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

record_step() {
  local step_name="$1"
  local status="$2"
  local exit_code="$3"
  local elapsed="$4"
  local cmd="$5"
  local log_path="$6"

  if [[ "$status" != "success" && "$status" != "skipped" ]]; then
    OVERALL_STATUS="failed"
  fi

  local safe_name
  local escaped_name escaped_status escaped_cmd escaped_log
  safe_name="$(echo "$step_name" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')"
  escaped_name="$(printf '%s' "$step_name" | json_escape)"
  escaped_status="$(printf '%s' "$status" | json_escape)"
  escaped_cmd="$(printf '%s' "$cmd" | json_escape)"
  escaped_log="$(printf '%s' "$log_path" | json_escape)"

  STEP_ROWS+="{\"step\":\"${safe_name}\",\"name\":\"${escaped_name}\",\"status\":\"${escaped_status}\",\"exit_code\":${exit_code},\"elapsed_s\":${elapsed},\"command\":\"${escaped_cmd}\",\"log_path\":\"${escaped_log}\"},"
}

run_step() {
  local step_name="$1"
  local command="$2"
  local step_log="$3"
  local start_ts
  start_ts="$(date +%s)"

  log "STEP: ${step_name}"
  log "CMD: ${command}"

  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[DRY RUN] %s\n' "$command" > "$step_log"
    local elapsed=$(( $(date +%s) - start_ts ))
    record_step "$step_name" "dry_run" 0 "$elapsed" "$command" "$step_log"
    return 0
  fi

  set +e
  bash -lc "$command" >"$step_log" 2>&1
  local code=$?
  set -e

  local elapsed=$(( $(date +%s) - start_ts ))
  if [[ $code -eq 0 ]]; then
    log "PASS: ${step_name}"
    record_step "$step_name" "success" "$code" "$elapsed" "$command" "$step_log"
  else
    log "FAIL: ${step_name} (exit ${code})"
    record_step "$step_name" "failed" "$code" "$elapsed" "$command" "$step_log"
    return "$code"
  fi
}

seed_demo_data() {
  local now
  now="$(date -u +%Y-%m-%d)"
  cat > "$DERIVED_DIR/metrics/scoreboard.json" <<EOF
[
  {
    "market_id": "${MARKET_ID}",
    "window": "90d",
    "as_of": "${START_UTC}",
    "category": "operational",
    "liquidity_bucket": "mid",
    "trust_score": 77.0,
    "brier": 0.13,
    "logloss": 0.25,
    "ece": 0.06
  }
]
EOF

  printf '[]\n' > "$DERIVED_DIR/alerts/alerts.json"
  cat > "$DERIVED_DIR/reports/postmortem/${MARKET_ID}_${now}.md" <<EOF
# Postmortem ${MARKET_ID}

- generated_at: ${START_UTC}
- source: rollout_gate_hardening_seed

## Summary

Smoke fixture for rollout hardening checks.
EOF
}

start_api() {
  export DERIVED_DIR="$DERIVED_DIR"
  export TSFM_FORECAST_API_TOKEN="$AUTH_TOKEN"

  log "Preparing API fixture in ${DERIVED_DIR}"
  seed_demo_data

  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Required Python binary not found: ${PYTHON_BIN}" >&2
    exit 1
  fi

  if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11+ is required (detected via ${PYTHON_BIN})." >&2
    exit 1
  fi

  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$API_PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    echo "Port ${API_PORT} is already in use; trying to proceed only when /metrics is healthy on ${API_BASE}." >&2
  fi

  local elapsed=0
  while true; do
    if curl -sS "$API_BASE/metrics" >/dev/null 2>&1; then
      log "API already healthy at ${API_BASE}/metrics"
      return 0
    fi
    ((elapsed += 1))
    if (( elapsed >= 3 )); then
      break
    fi
    sleep 1
  done

  log "Starting API server at ${API_BASE}"
  "$PYTHON_BIN" -m uvicorn api.app:app --host "$API_HOST" --port "$API_PORT" >"$GATE_LOG_DIR/api.log" 2>&1 &
  API_PID=$!

  log "Waiting for API health at ${API_BASE}/metrics (timeout ${HEALTH_TIMEOUT_SEC}s)"
  local tick=0
  while (( tick < HEALTH_TIMEOUT_SEC )); do
    if curl -sS "$API_BASE/metrics" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    tick=$((tick + 1))
  done

  echo "API did not become healthy in ${HEALTH_TIMEOUT_SEC}s. See ${GATE_LOG_DIR}/api.log" >&2
  return 1
}

cleanup() {
  if [[ -n "${API_PID}" && -n "${API_PID}" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
    wait "$API_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ "$DRY_RUN" == "1" ]]; then
  log "Dry run enabled"
fi

if ! start_api; then
  OVERALL_STATUS="failed"
  log "Failed to start or detect API"
  exit 1
fi

run_step "Live demo smoke" "API_BASE=$API_BASE AUTH_TOKEN=$AUTH_TOKEN MARKET_ID=$MARKET_ID REPORT_PATH=$REPORT_DIR/live_demo_smoke_report.md "$PYTHON_BIN" scripts/live_demo_smoke.sh" "$GATE_LOG_DIR/live_demo_smoke.log"

run_step "Live demo security checks" "API_BASE=$API_BASE AUTH_TOKEN=$AUTH_TOKEN AUTO_START_API=0 REPORT_PATH=$REPORT_DIR/live_demo_security_report.md TSFM_FORECAST_API_TOKEN=$AUTH_TOKEN "$PYTHON_BIN" scripts/live_demo_security_check.sh" "$GATE_LOG_DIR/live_demo_security.log"

run_step "PRD2 runtime metrics smoke" "PYTHONPATH=. $PYTHON_BIN scripts/prd2_runtime_metrics_smoke.py" "$GATE_LOG_DIR/runtime_metrics_smoke.log"

run_step "Perf benchmark sanity" "PYTHONPATH=. $PYTHON_BIN pipelines/bench_tsfm_runner_perf.py --requests ${PERF_REQUESTS} --unique ${PERF_UNIQUE} --adapter-latency-ms ${PERF_LATENCY_MS} --budget-p95-ms ${PERF_P95_MS} --budget-cycle-s ${PERF_CYCLE_S} | tee ${GATE_LOG_DIR}/perf_bench.log && python scripts/validate_prd2_perf_bench.py --input ${GATE_LOG_DIR}/perf_bench.log --output ${GATE_LOG_DIR}/perf_bench_result.json --p95-threshold-ms ${PERF_P95_MS} --cycle-threshold-s ${PERF_CYCLE_S}" "$GATE_LOG_DIR/perf_benchmark_full.log"

run_step "OpenAPI smoke" "PYTHONPATH=. $PYTHON_BIN scripts/openapi_smoke.py --base-url ${API_BASE} --output ${GATE_LOG_DIR}/openapi_smoke_report.json" "$GATE_LOG_DIR/openapi_smoke.log"

END_EPOCH="$(date +%s)"
END_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOTAL_ELAPSED="$((END_EPOCH - START_EPOCH))"

if [[ -n "$STEP_ROWS" ]]; then
  STEP_ROWS="[${STEP_ROWS%,}]"
else
  STEP_ROWS="[]"
fi

SUMMARY_PATH="$REPORT_DIR/rollout_hardening_gate_summary.json"
cat > "$SUMMARY_PATH" <<EOF
{
  "run_started_at_utc": "${START_UTC}",
  "run_finished_at_utc": "${END_UTC}",
  "total_elapsed_s": ${TOTAL_ELAPSED},
  "overall_status": "${OVERALL_STATUS}",
  "dry_run": ${DRY_RUN},
  "api_base": "${API_BASE}",
  "steps": ${STEP_ROWS}
}
EOF

log "Summary written: ${SUMMARY_PATH}"

if [[ "$OVERALL_STATUS" != "success" ]]; then
  log "Rollout hardening gate failed"
  exit 1
fi

log "Rollout hardening gate succeeded"
