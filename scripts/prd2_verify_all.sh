#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
LOG_DIR="${ARTIFACT_DIR}/prd2_verify_logs"
SUMMARY_PATH="${ARTIFACT_DIR}/prd2_verify_summary.json"
DRY_RUN="${PRD2_VERIFY_DRY_RUN:-0}"
PYTHON_BIN="${PRD2_VERIFY_PYTHON_BIN:-python3}"

mkdir -p "${LOG_DIR}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] $*"
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

STEP_ROWS=""
OVERALL_STATUS="success"
START_EPOCH="$(date +%s)"
START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

if [[ "${DRY_RUN}" != "1" ]]; then
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    log "ERROR: Python binary not found: ${PYTHON_BIN}"
    exit 1
  fi

  if ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    log "ERROR: ${PYTHON_BIN} must be Python >= 3.11 (StrEnum required by current PRD2 codepath)."
    log "TIP: PRD2_VERIFY_PYTHON_BIN=python3.11 scripts/prd2_verify_all.sh"
    exit 1
  fi
fi

run_step() {
  local step_name="$1"
  local command="$2"
  local step_index="$3"
  local safe_name
  safe_name="$(echo "${step_name}" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')"
  local log_path="${LOG_DIR}/$(printf '%02d' "${step_index}")_${safe_name}.log"
  local step_start="$(date +%s)"

  log "STEP ${step_index}: ${step_name}"
  log "CMD: ${command}"

  local status="success"
  local exit_code=0

  if [[ "${DRY_RUN}" == "1" ]]; then
    status="dry_run"
    printf '[DRY RUN] %s\n' "${command}" > "${log_path}"
  else
    set +e
    (
      cd "${ROOT_DIR}"
      bash -lc "${command}"
    ) >"${log_path}" 2>&1
    exit_code=$?
    set -e

    if [[ ${exit_code} -ne 0 ]]; then
      status="failed"
      OVERALL_STATUS="failed"
      log "FAIL: ${step_name} (exit ${exit_code})"
    else
      log "PASS: ${step_name}"
    fi
  fi

  local step_end="$(date +%s)"
  local elapsed="$((step_end - step_start))"

  local escaped_name escaped_cmd escaped_log escaped_status
  escaped_name="$(printf '%s' "${step_name}" | json_escape)"
  escaped_cmd="$(printf '%s' "${command}" | json_escape)"
  escaped_log="$(printf '%s' "${log_path}" | json_escape)"
  escaped_status="$(printf '%s' "${status}" | json_escape)"

  STEP_ROWS+="{\"step\":${step_index},\"name\":\"${escaped_name}\",\"command\":\"${escaped_cmd}\",\"status\":\"${escaped_status}\",\"exit_code\":${exit_code},\"elapsed_s\":${elapsed},\"log_path\":\"${escaped_log}\"},"
}

run_step "PRD2 unit selection" "${PYTHON_BIN} -m pytest -q tests/unit/test_tsfm_runner_service.py tests/unit/test_tsfm_perf_smoke.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py tests/unit/test_baseline_bands.py tests/unit/test_tsfm_base_contract.py" 1
run_step "PRD2 integration selection" "${PYTHON_BIN} -m pytest -q tests/integration/test_tollama_live_integration.py" 2
run_step "PRD2 performance benchmark" "PYTHONPATH=. ${PYTHON_BIN} pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 20 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60" 3
run_step "PRD2 release audit" "PYTHON_BIN=${PYTHON_BIN} ${PYTHON_BIN} scripts/prd2_release_audit.py --python-bin ${PYTHON_BIN}" 4

END_EPOCH="$(date +%s)"
END_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOTAL_ELAPSED="$((END_EPOCH - START_EPOCH))"

if [[ -n "${STEP_ROWS}" ]]; then
  STEP_ROWS="[${STEP_ROWS%,}]"
else
  STEP_ROWS="[]"
fi

cat > "${SUMMARY_PATH}" <<EOF
{
  "run_started_at_utc": "${START_UTC}",
  "run_finished_at_utc": "${END_UTC}",
  "total_elapsed_s": ${TOTAL_ELAPSED},
  "overall_status": "${OVERALL_STATUS}",
  "dry_run": ${DRY_RUN},
  "summary_path": "${SUMMARY_PATH}",
  "steps": ${STEP_ROWS}
}
EOF

log "Wrote summary: ${SUMMARY_PATH}"

if [[ "${OVERALL_STATUS}" != "success" ]]; then
  log "PRD2 one-command verification failed. See logs in ${LOG_DIR}"
  exit 1
fi

log "PRD2 one-command verification succeeded."
