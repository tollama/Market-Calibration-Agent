#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "${ROOT_DIR}/.." && pwd)"

NEWS_AGENT_DIR="${NEWS_AGENT_DIR:-${WORKSPACE_DIR}/News-Agent}"
FINANCIAL_AGENT_DIR="${FINANCIAL_AGENT_DIR:-${WORKSPACE_DIR}/Financial-Agent}"
TOLLAMA_DIR="${TOLLAMA_DIR:-${WORKSPACE_DIR}/tollama}"
TOLLAMA_PYTHONPATH="${TOLLAMA_PYTHONPATH:-${TOLLAMA_DIR}/src}"

PYTHON311_BIN="${PYTHON311_BIN:-python3.11}"

NEWS_PORT="${NEWS_PORT:-8090}"
FINANCIAL_PORT="${FINANCIAL_PORT:-8091}"
MCA_PORT="${MCA_PORT:-8001}"
TOLLAMA_PORT="${TOLLAMA_PORT:-11435}"

NEWS_BASE_URL="http://127.0.0.1:${NEWS_PORT}"
FINANCIAL_BASE_URL="http://127.0.0.1:${FINANCIAL_PORT}"
MCA_BASE_URL="http://127.0.0.1:${MCA_PORT}"
TOLLAMA_BASE_URL="http://127.0.0.1:${TOLLAMA_PORT}"

NEWS_AGENT_DATA_DIR="${NEWS_AGENT_DATA_DIR:-/tmp/news-agent-smoke}"
REPORT_PATH="${REPORT_PATH:-${ROOT_DIR}/artifacts/federation/federation_smoke_report.md}"
CURL_TIMEOUT="${CURL_TIMEOUT:-20}"

mkdir -p "$(dirname "${REPORT_PATH}")"
mkdir -p "${NEWS_AGENT_DATA_DIR}"

TMP_DIR="$(mktemp -d)"
PIDS=()
SUMMARY_LINES=()
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0
API_CALL_OUT=""

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

record_result() {
  local status="$1"
  local name="$2"
  local detail="$3"
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  if [[ "${status}" == "PASS" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  SUMMARY_LINES+=("- [${status}] ${name}: ${detail}")
  echo "[${status}] ${name} - ${detail}"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS -m "${CURL_TIMEOUT}" "${url}" >/dev/null 2>&1; then
      record_result "PASS" "${name}" "ready at ${url}"
      return 0
    fi
    sleep 1
  done
  record_result "FAIL" "${name}" "not reachable at ${url}"
  return 1
}

start_bg() {
  local name="$1"
  local workdir="$2"
  shift 2
  (
    cd "${workdir}"
    "$@"
  ) >"${TMP_DIR}/${name}.log" 2>&1 &
  local pid=$!
  PIDS+=("${pid}")
  echo "[INFO] started ${name} pid=${pid}"
}

seed_news_fixture() {
  "${PYTHON311_BIN}" - <<'PY'
import json
import os
from pathlib import Path

base_dir = Path(os.environ["NEWS_AGENT_DATA_DIR"])
if base_dir.exists():
    for path in sorted(base_dir.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
base_dir.mkdir(parents=True, exist_ok=True)
payload_dir = base_dir / "trust_payloads" / "dt=2026-03-18"
payload_dir.mkdir(parents=True, exist_ok=True)
payload_path = payload_dir / "seed.jsonl"
record = {
    "story_id": "story-smoke-001",
    "source_credibility": 0.91,
    "corroboration": 0.82,
    "contradiction_score": 0.05,
    "propagation_delay_seconds": 45.0,
    "freshness_score": 0.97,
    "novelty": 0.33,
}
payload_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
print(payload_path)
PY
}

json_field() {
  local file="$1"
  local expr="$2"
  "${PYTHON311_BIN}" - "$file" "$expr" <<'PY'
import json
import sys
from typing import Any

path, expr = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as handle:
    data = json.load(handle)

cur: Any = data
for token in expr.split("."):
    if not token:
        continue
    if token.endswith("]") and "[" in token:
        field, index = token[:-1].split("[", 1)
        if field:
            cur = cur.get(field)
        cur = cur[int(index)]
    else:
        cur = cur.get(token)

if isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
elif cur is None:
    print("")
else:
    print(cur)
PY
}

api_call() {
  local name="$1"
  local method="$2"
  local url="$3"
  local body="${4:-}"
  local out="${TMP_DIR}/${name}.json"
  local code
  API_CALL_OUT=""
  if [[ -n "${body}" ]]; then
    code="$(curl -sS -m "${CURL_TIMEOUT}" -o "${out}" -w "%{http_code}" -X "${method}" "${url}" -H "Content-Type: application/json" --data "${body}")" || {
      record_result "FAIL" "${name}" "curl failed"
      return 1
    }
  else
    code="$(curl -sS -m "${CURL_TIMEOUT}" -o "${out}" -w "%{http_code}" -X "${method}" "${url}")" || {
      record_result "FAIL" "${name}" "curl failed"
      return 1
    }
  fi

  if [[ "${code}" =~ ^2 ]]; then
    record_result "PASS" "${name}" "HTTP ${code}"
    API_CALL_OUT="${out}"
    return 0
  fi

  local detail
  detail="$(tr '\n' ' ' < "${out}" | cut -c1-240)"
  record_result "FAIL" "${name}" "HTTP ${code} body=${detail}"
  return 1
}

api_call_with_retry() {
  local attempts="$1"
  shift
  local attempt
  for attempt in $(seq 1 "${attempts}"); do
    if api_call "$@"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

write_report() {
  {
    echo "# Federation Smoke Report"
    echo
    echo "- generated_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "- workspace: ${WORKSPACE_DIR}"
    echo "- pass_count: ${PASS_COUNT}"
    echo "- fail_count: ${FAIL_COUNT}"
    echo "- total_count: ${TOTAL_COUNT}"
    echo
    echo "## Summary"
    printf '%s\n' "${SUMMARY_LINES[@]}"
  } > "${REPORT_PATH}"
}

require_cmd curl
require_cmd "${PYTHON311_BIN}"
require_cmd uv

echo "[STEP] seed persisted News-Agent fixture"
export NEWS_AGENT_DATA_DIR
seed_news_fixture >/dev/null

echo "[STEP] start News-Agent"
start_bg "news_agent" "${NEWS_AGENT_DIR}" env NEWS_AGENT_DATA_DIR="${NEWS_AGENT_DATA_DIR}" uv run --python "${PYTHON311_BIN}" uvicorn api.routes:app --host 127.0.0.1 --port "${NEWS_PORT}"
wait_for_http "news_agent_health" "${NEWS_BASE_URL}/api/v1/news/health"

echo "[STEP] start Financial-Agent"
start_bg "financial_agent" "${FINANCIAL_AGENT_DIR}" uv run --python "${PYTHON311_BIN}" uvicorn api.routes:app --host 127.0.0.1 --port "${FINANCIAL_PORT}"
wait_for_http "financial_agent_health" "${FINANCIAL_BASE_URL}/api/v1/financial/health"

echo "[STEP] start MCA"
start_bg "mca" "${ROOT_DIR}" uv run --python "${PYTHON311_BIN}" uvicorn api.app:app --host 127.0.0.1 --port "${MCA_PORT}"
wait_for_http "mca_markets" "${MCA_BASE_URL}/markets"

echo "[STEP] start tollama live federation"
start_bg "tollama" "${TOLLAMA_DIR}" env PYTHONPATH="${TOLLAMA_PYTHONPATH}" TOLLAMA_USE_LIVE_CONNECTORS=true NEWS_AGENT_URL="${NEWS_BASE_URL}" FINANCIAL_AGENT_URL="${FINANCIAL_BASE_URL}" TOLLAMA_HOST="127.0.0.1:${TOLLAMA_PORT}" TOLLAMA_LOG_LEVEL=info uv run --python "${PYTHON311_BIN}" python -m tollama.daemon.main
wait_for_http "tollama_health" "${TOLLAMA_BASE_URL}/v1/health"

echo "[STEP] verify direct service payloads"
api_call "news_story" GET "${NEWS_BASE_URL}/stories/story-smoke-001"
news_payload_file="${API_CALL_OUT}"
api_call "financial_instrument" GET "${FINANCIAL_BASE_URL}/instruments/AAPL"
financial_payload_file="${API_CALL_OUT}"
api_call "mca_trust_explanation" GET "${MCA_BASE_URL}/markets/mkt-90/trust-explanation"
mca_trust_file="${API_CALL_OUT}"
api_call_with_retry 10 "tollama_connectors" POST "${TOLLAMA_BASE_URL}/api/xai/connectors/health" '{}'
tollama_connectors_file="${API_CALL_OUT}"

news_story_id="$(json_field "${news_payload_file}" "story_id")"
news_contradiction_score="$(json_field "${news_payload_file}" "contradiction_score")"
financial_liquidity="$(json_field "${financial_payload_file}" "liquidity_depth")"
mca_market_id="$(json_field "${mca_trust_file}" "market_id")"
financial_connector_status="$(json_field "${tollama_connectors_file}" "connectors[0].status")"
news_connector_status="$(json_field "${tollama_connectors_file}" "connectors[1].status")"

if [[ "${news_story_id}" == "story-smoke-001" ]]; then
  record_result "PASS" "news_fixture_payload" "story_id=${news_story_id}"
else
  record_result "FAIL" "news_fixture_payload" "unexpected story_id=${news_story_id}"
fi

if [[ "${news_contradiction_score}" == "0.05" ]]; then
  record_result "PASS" "news_contradiction_raw" "contradiction_score=${news_contradiction_score}"
else
  record_result "FAIL" "news_contradiction_raw" "unexpected contradiction_score=${news_contradiction_score}"
fi

if [[ -n "${financial_liquidity}" && "${financial_liquidity}" != "0" && "${financial_liquidity}" != "0.0" ]]; then
  record_result "PASS" "financial_provider_payload" "liquidity_depth=${financial_liquidity}"
else
  record_result "FAIL" "financial_provider_payload" "empty/default liquidity_depth=${financial_liquidity}"
fi

if [[ "${mca_market_id}" == "mkt-90" ]]; then
  record_result "PASS" "mca_trust_payload" "market_id=${mca_market_id}"
else
  record_result "FAIL" "mca_trust_payload" "unexpected market_id=${mca_market_id}"
fi

if [[ "${financial_connector_status}" == "available" && "${news_connector_status}" == "available" ]]; then
  record_result "PASS" "tollama_connector_health" "news=${news_connector_status} financial=${financial_connector_status}"
else
  record_result "FAIL" "tollama_connector_health" "news=${news_connector_status} financial=${financial_connector_status}"
fi

echo "[STEP] verify tollama remote assembly"
assembly_out="${TMP_DIR}/assembler.json"
env \
  TOLLAMA_USE_LIVE_CONNECTORS=true \
  NEWS_AGENT_URL="${NEWS_BASE_URL}" \
  FINANCIAL_AGENT_URL="${FINANCIAL_BASE_URL}" \
  PYTHONPATH="${TOLLAMA_DIR}/src" \
  "${PYTHON311_BIN}" - <<'PY' > "${assembly_out}"
import json

from tollama.xai.connectors.helpers import build_default_assembler
from tollama.xai.trust_router import build_default_trust_router

assembler = build_default_assembler()
router = build_default_trust_router()

news = assembler.assemble("news", "story-smoke-001")
financial = assembler.assemble("financial_market", "AAPL")

news_result = router.analyze(context=news.trust_context, payload=news.payload)
financial_result = router.analyze(context=financial.trust_context, payload=financial.payload)

print(json.dumps({
    "news_payload": news.payload,
    "financial_payload": financial.payload,
    "news_result": {
        "agent_name": news_result.agent_name,
        "trust_score": news_result.trust_score,
        "risk_category": news_result.risk_category,
        "contradiction_component_value": news_result.component_breakdown["contradiction_penalty"].value,
        "contradiction_component_score": news_result.component_breakdown["contradiction_penalty"].score,
    },
    "financial_result": {
        "agent_name": financial_result.agent_name,
        "trust_score": financial_result.trust_score,
        "risk_category": financial_result.risk_category,
    },
}, default=str))
PY

assembled_story_id="$(json_field "${assembly_out}" "news_payload.story_id")"
assembled_news_contradiction_value="$(json_field "${assembly_out}" "news_result.contradiction_component_value")"
assembled_news_contradiction_score="$(json_field "${assembly_out}" "news_result.contradiction_component_score")"
assembled_financial_agent="$(json_field "${assembly_out}" "financial_result.agent_name")"

if [[ "${assembled_story_id}" == "story-smoke-001" ]]; then
  record_result "PASS" "tollama_news_assembly" "assembled story_id=${assembled_story_id}"
else
  record_result "FAIL" "tollama_news_assembly" "unexpected story_id=${assembled_story_id}"
fi

if [[ "${assembled_financial_agent}" == "financial_market" ]]; then
  record_result "PASS" "tollama_financial_assembly" "agent_name=${assembled_financial_agent}"
else
  record_result "FAIL" "tollama_financial_assembly" "unexpected agent_name=${assembled_financial_agent}"
fi

if [[ "${assembled_news_contradiction_value}" == "0.05" && "${assembled_news_contradiction_score}" == "0.95" ]]; then
  record_result "PASS" "tollama_news_contradiction_semantics" "value=${assembled_news_contradiction_value} score=${assembled_news_contradiction_score}"
else
  record_result "FAIL" "tollama_news_contradiction_semantics" "value=${assembled_news_contradiction_value} score=${assembled_news_contradiction_score}"
fi

write_report
echo
echo "[DONE] report written to ${REPORT_PATH}"

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "[FAIL] federation smoke encountered ${FAIL_COUNT} failure(s)" >&2
  exit 1
fi

echo "[PASS] federation smoke completed successfully"
