#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${APP_DIR}/../.." && pwd)"

THRESHOLDS_PATH="${REPO_ROOT}/configs/kpi_contract_thresholds.json"
KPI_SCRIPT="${REPO_ROOT}/scripts/kpi_contract_report.py"
KPI_BUILD_SCRIPT="${APP_DIR}/scripts/build_run_kpi_jsonl.ts"

AUTO_MODE="0"
INPUT_PATH=""
OUTPUT_PATH="${REPO_ROOT}/artifacts/ops/kpi_contract_report_canary_revalidate.json"
AUTO_EXECUTION_SOURCE="${APP_DIR}/scripts/examples/execution_runs_sample.jsonl"
AUTO_METRICS_SOURCE=""
AUTO_KPI_OUTPUT="${REPO_ROOT}/artifacts/ops/kpi_runs_auto.jsonl"
AUTO_UNMATCHED_POLICY="warn"
AUTO_TIME_TOLERANCE_SECONDS="300"

usage() {
  cat <<EOF
사용법:
  bash scripts/p1_revalidate.sh <kpi_input_jsonl_path> [output_json_path]
  bash scripts/p1_revalidate.sh --auto [옵션] [output_json_path]

자동 모드 옵션:
  --execution-source <path>      실행 지표 입력(JSON/JSONL)
  --metrics-source <path>        brier/ece 입력(JSON/JSONL; run-level 또는 scoreboard)
  --auto-kpi-output <path>       자동 생성된 KPI JSONL 출력 경로
  --on-unmatched <skip|warn|error>
  --time-tolerance-seconds <int>

예시:
  # 기존 수동 입력 방식
  bash scripts/p1_revalidate.sh ../../scripts/examples/kpi_runs_sample.jsonl

  # 자동 KPI 생성 + 재검증
  bash scripts/p1_revalidate.sh --auto \
    --execution-source scripts/examples/execution_runs_sample.jsonl \
    --metrics-source scripts/examples/metrics_runs_sample.jsonl \
    --auto-kpi-output ../../artifacts/ops/kpi_runs_auto.jsonl
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --auto)
      AUTO_MODE="1"
      shift
      ;;
    --execution-source)
      AUTO_EXECUTION_SOURCE="$2"
      shift 2
      ;;
    --metrics-source)
      AUTO_METRICS_SOURCE="$2"
      shift 2
      ;;
    --auto-kpi-output)
      AUTO_KPI_OUTPUT="$2"
      shift 2
      ;;
    --on-unmatched)
      AUTO_UNMATCHED_POLICY="$2"
      shift 2
      ;;
    --time-tolerance-seconds)
      AUTO_TIME_TOLERANCE_SECONDS="$2"
      shift 2
      ;;
    *)
      if [[ -z "${INPUT_PATH}" ]]; then
        INPUT_PATH="$1"
      elif [[ -z "${OUTPUT_PATH_OVERRIDE:-}" ]]; then
        OUTPUT_PATH_OVERRIDE="$1"
      else
        echo "[ERROR] 알 수 없는 인자: $1" >&2
        usage
        exit 2
      fi
      shift
      ;;
  esac
done

if [[ "${AUTO_MODE}" == "1" && -n "${INPUT_PATH}" && -z "${OUTPUT_PATH_OVERRIDE:-}" ]]; then
  OUTPUT_PATH_OVERRIDE="${INPUT_PATH}"
  INPUT_PATH=""
fi

if [[ -n "${OUTPUT_PATH_OVERRIDE:-}" ]]; then
  OUTPUT_PATH="${OUTPUT_PATH_OVERRIDE}"
fi

abs_path() {
  local p="$1"
  if [[ "$p" == /* ]]; then
    echo "$p"
  else
    echo "${APP_DIR}/$p"
  fi
}

if [[ "${AUTO_MODE}" == "1" ]]; then
  AUTO_EXECUTION_SOURCE="$(abs_path "${AUTO_EXECUTION_SOURCE}")"
  AUTO_KPI_OUTPUT="$(abs_path "${AUTO_KPI_OUTPUT}")"
  if [[ -n "${AUTO_METRICS_SOURCE}" ]]; then
    AUTO_METRICS_SOURCE="$(abs_path "${AUTO_METRICS_SOURCE}")"
  fi

  if [[ ! -f "${KPI_BUILD_SCRIPT}" ]]; then
    echo "[ERROR] KPI build 스크립트를 찾을 수 없습니다: ${KPI_BUILD_SCRIPT}" >&2
    exit 2
  fi
  if [[ ! -f "${AUTO_EXECUTION_SOURCE}" ]]; then
    echo "[ERROR] execution source 파일을 찾을 수 없습니다: ${AUTO_EXECUTION_SOURCE}" >&2
    exit 2
  fi

  echo "[STEP] run-level KPI JSONL 자동 생성"
  BUILD_CMD=(
    npx tsx "${KPI_BUILD_SCRIPT}"
    --execution-source "${AUTO_EXECUTION_SOURCE}"
    --output "${AUTO_KPI_OUTPUT}"
    --on-unmatched "${AUTO_UNMATCHED_POLICY}"
    --time-tolerance-seconds "${AUTO_TIME_TOLERANCE_SECONDS}"
  )
  if [[ -n "${AUTO_METRICS_SOURCE}" ]]; then
    if [[ ! -f "${AUTO_METRICS_SOURCE}" ]]; then
      echo "[ERROR] metrics source 파일을 찾을 수 없습니다: ${AUTO_METRICS_SOURCE}" >&2
      exit 2
    fi
    BUILD_CMD+=(--metrics-source "${AUTO_METRICS_SOURCE}")
  fi

  (
    cd "${APP_DIR}"
    "${BUILD_CMD[@]}"
  )

  INPUT_PATH="${AUTO_KPI_OUTPUT}"
fi

if [[ -z "${INPUT_PATH}" ]]; then
  usage
  exit 2
fi

INPUT_PATH="$(abs_path "${INPUT_PATH}")"
OUTPUT_PATH="$(abs_path "${OUTPUT_PATH}")"

if [[ ! -f "${INPUT_PATH}" ]]; then
  echo "[ERROR] KPI input 파일을 찾을 수 없습니다: ${INPUT_PATH}" >&2
  exit 2
fi
if [[ ! -f "${KPI_SCRIPT}" ]]; then
  echo "[ERROR] KPI 스크립트를 찾을 수 없습니다: ${KPI_SCRIPT}" >&2
  exit 2
fi
if [[ ! -f "${THRESHOLDS_PATH}" ]]; then
  echo "[ERROR] 임계값 파일을 찾을 수 없습니다: ${THRESHOLDS_PATH}" >&2
  exit 2
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")"

echo "[STEP] smoke:ci 실행"
(
  cd "${APP_DIR}"
  npm run smoke:ci
)

echo "[STEP] KPI 5-run 리포트 실행"
python3 "${KPI_SCRIPT}" \
  --input "${INPUT_PATH}" \
  --stage canary \
  --n 5 \
  --thresholds "${THRESHOLDS_PATH}" \
  --output-json "${OUTPUT_PATH}"

echo "[STEP] KPI overall 판정 확인"
KPI_PARSE_LINE="$(python3 - <<'PY' "${OUTPUT_PATH}"
import json, sys

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)

path = "UNKNOWN"
value = "UNKNOWN"

summary = data.get('summary') if isinstance(data, dict) else None
if isinstance(summary, dict) and 'overall' in summary:
    path = 'summary.overall'
    value = summary.get('overall')
elif isinstance(data, dict) and 'overall' in data:
    path = 'overall'
    value = data.get('overall')

parsed = 'UNKNOWN' if value is None else str(value)
raw = repr(value)
print(f"{path}\t{parsed}\t{raw}")
PY
)"

IFS=$'\t' read -r OVERALL_PATH OVERALL OVERALL_RAW <<< "${KPI_PARSE_LINE}"
OVERALL_PATH="${OVERALL_PATH:-UNKNOWN}"
OVERALL="${OVERALL:-UNKNOWN}"
OVERALL_RAW="${OVERALL_RAW:-None}"

echo "[INFO] KPI overall=${OVERALL} (path=${OVERALL_PATH}, raw=${OVERALL_RAW})"
if [[ "${OVERALL}" != "GO" ]]; then
  echo "[FAIL] KPI overall이 GO가 아닙니다. (path=${OVERALL_PATH}, parsed=${OVERALL}, raw=${OVERALL_RAW})" >&2
  exit 1
fi

echo "[DONE] 재검증 완료: smoke:ci PASS + KPI overall=GO"
echo "[DONE] KPI input: ${INPUT_PATH}"
echo "[DONE] 리포트: ${OUTPUT_PATH}"
