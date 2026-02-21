#!/usr/bin/env bash
set -u

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
REPORT_PATH="${REPORT_PATH:-artifacts/demo/live_demo_smoke_report.md}"
AUTH_TOKEN="${TSFM_FORECAST_API_TOKEN:-${AUTH_TOKEN:-tsfm-dev-token}}"
CURL_TIMEOUT="${CURL_TIMEOUT:-15}"
MARKET_ID_INPUT="${MARKET_ID:-}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p "$(dirname "$REPORT_PATH")"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0
SUMMARY_LINES=()
KEY_LINES=()

record_result() {
  local status="$1"
  local name="$2"
  local detail="$3"
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  if [[ "$status" == "PASS" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  SUMMARY_LINES+=("- [${status}] ${name}: ${detail}")
  echo "[${status}] ${name} - ${detail}"
}

extract_json() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json
import sys
from typing import Any

path, expr = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

cur: Any = data
for token in expr.split("."):
    if token == "":
        continue
    if token.endswith("]") and "[" in token:
        field, idx = token[:-1].split("[", 1)
        if field:
            cur = cur.get(field)
        cur = cur[int(idx)]
    else:
        if isinstance(cur, dict):
            cur = cur.get(token)
        else:
            raise SystemExit(1)

if isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
elif cur is None:
    print("")
else:
    print(cur)
PY
}

API_CALL_OUT=""
api_call() {
  local name="$1"
  local method="$2"
  local url="$3"
  local body_file="${4:-}"
  local auth="${5:-no}"

  local out_body="$TMP_DIR/${name}.json"
  local out_code="$TMP_DIR/${name}.code"
  local out_head="$TMP_DIR/${name}.head"
  API_CALL_OUT=""

  local -a curl_args
  curl_args=(
    -sS
    -m "$CURL_TIMEOUT"
    -o "$out_body"
    -D "$out_head"
    -w "%{http_code}"
    -X "$method"
    "$url"
    -H "Content-Type: application/json"
  )

  if [[ "$auth" == "yes" ]]; then
    curl_args+=( -H "Authorization: Bearer ${AUTH_TOKEN}" )
  fi
  if [[ -n "$body_file" ]]; then
    curl_args+=( --data "@${body_file}" )
  fi

  local code=""
  local attempt
  for attempt in 1 2; do
    if ! curl "${curl_args[@]}" >"$out_code" 2>"$TMP_DIR/${name}.err"; then
      record_result "FAIL" "$name" "curl error: $(tr '\n' ' ' < "$TMP_DIR/${name}.err")"
      return 1
    fi
    code="$(cat "$out_code")"

    if [[ "$code" == "429" && "$attempt" -eq 1 ]]; then
      local retry_after
      retry_after="$(awk 'tolower($1)=="retry-after:" {gsub("\r", "", $2); print $2}' "$out_head" | tail -n1)"
      if [[ -z "$retry_after" || ! "$retry_after" =~ ^[0-9]+$ ]]; then
        retry_after=2
      fi
      sleep "$retry_after"
      continue
    fi
    break
  done

  if [[ "$code" =~ ^2 ]]; then
    record_result "PASS" "$name" "HTTP ${code}"
    API_CALL_OUT="$out_body"
    return 0
  fi

  local detail
  detail="$(tr '\n' ' ' < "$out_body" | cut -c1-240)"
  record_result "FAIL" "$name" "HTTP ${code} body=${detail}"
  return 1
}

printf "\n=== Live Demo API Smoke ===\n"
printf "API_BASE=%s\n\n" "$API_BASE"

SCOREBOARD_FILE=""
ALERTS_FILE=""
MARKETS_FILE=""
MARKET_DETAIL_FILE=""
MARKET_METRICS_FILE=""
POSTMORTEM_FILE=""
COMPARISON_FILE=""
TSFM_FILE=""
MARKET_ID=""

api_call "api_up_scoreboard" GET "${API_BASE}/scoreboard" "" no || true
SCOREBOARD_FILE="$API_CALL_OUT"
if [[ -n "$SCOREBOARD_FILE" && -s "$SCOREBOARD_FILE" ]]; then
  sb_total="$(extract_json "$SCOREBOARD_FILE" "total" 2>/dev/null || echo "")"
  first_market="$(extract_json "$SCOREBOARD_FILE" "items[0].market_id" 2>/dev/null || echo "")"
  KEY_LINES+=("- scoreboard.total: ${sb_total:-N/A}")
  [[ -n "$first_market" ]] && KEY_LINES+=("- scoreboard.first_market_id: ${first_market}")
fi

api_call "alerts" GET "${API_BASE}/alerts?limit=5" "" no || true
ALERTS_FILE="$API_CALL_OUT"
if [[ -n "$ALERTS_FILE" && -s "$ALERTS_FILE" ]]; then
  alerts_total="$(extract_json "$ALERTS_FILE" "total" 2>/dev/null || echo "")"
  alerts_first_sev="$(extract_json "$ALERTS_FILE" "items[0].severity" 2>/dev/null || echo "")"
  KEY_LINES+=("- alerts.total: ${alerts_total:-N/A}")
  [[ -n "$alerts_first_sev" ]] && KEY_LINES+=("- alerts.first_severity: ${alerts_first_sev}")
fi

api_call "markets" GET "${API_BASE}/markets" "" no || true
MARKETS_FILE="$API_CALL_OUT"
if [[ -n "$MARKETS_FILE" && -s "$MARKETS_FILE" ]]; then
  MARKET_ID="$(extract_json "$MARKETS_FILE" "items[0].market_id" 2>/dev/null || echo "")"
  markets_total="$(extract_json "$MARKETS_FILE" "total" 2>/dev/null || echo "")"
  KEY_LINES+=("- markets.total: ${markets_total:-N/A}")
fi

if [[ -n "$MARKET_ID_INPUT" ]]; then
  MARKET_ID="$MARKET_ID_INPUT"
fi
if [[ -z "$MARKET_ID" && -n "$SCOREBOARD_FILE" && -s "$SCOREBOARD_FILE" ]]; then
  MARKET_ID="$(extract_json "$SCOREBOARD_FILE" "items[0].market_id" 2>/dev/null || echo "")"
fi
if [[ -z "$MARKET_ID" ]]; then
  MARKET_ID="demo-market"
fi
KEY_LINES+=("- selected.market_id: ${MARKET_ID}")

api_call "market_detail" GET "${API_BASE}/markets/${MARKET_ID}" "" no || true
MARKET_DETAIL_FILE="$API_CALL_OUT"
if [[ -n "$MARKET_DETAIL_FILE" && -s "$MARKET_DETAIL_FILE" ]]; then
  trust_score="$(extract_json "$MARKET_DETAIL_FILE" "trust_score" 2>/dev/null || echo "")"
  category="$(extract_json "$MARKET_DETAIL_FILE" "category" 2>/dev/null || echo "")"
  [[ -n "$trust_score" ]] && KEY_LINES+=("- market_detail.trust_score: ${trust_score}")
  [[ -n "$category" ]] && KEY_LINES+=("- market_detail.category: ${category}")
fi

api_call "market_metrics" GET "${API_BASE}/markets/${MARKET_ID}/metrics" "" no || true
MARKET_METRICS_FILE="$API_CALL_OUT"
if [[ -n "$MARKET_METRICS_FILE" && -s "$MARKET_METRICS_FILE" ]]; then
  alert_total="$(extract_json "$MARKET_METRICS_FILE" "alert_total" 2>/dev/null || echo "")"
  KEY_LINES+=("- market_metrics.alert_total: ${alert_total:-N/A}")
fi

api_call "postmortem_mkt90" GET "${API_BASE}/postmortem/mkt-90" "" no || true
POSTMORTEM_FILE="$API_CALL_OUT"
if [[ -n "$POSTMORTEM_FILE" && -s "$POSTMORTEM_FILE" ]]; then
  pm_source="$(extract_json "$POSTMORTEM_FILE" "source" 2>/dev/null || echo "")"
  pm_title="$(extract_json "$POSTMORTEM_FILE" "title" 2>/dev/null || echo "")"
  [[ -n "$pm_source" ]] && KEY_LINES+=("- postmortem.mkt90.source: ${pm_source}")
  [[ -n "$pm_title" ]] && KEY_LINES+=("- postmortem.mkt90.title: ${pm_title}")
fi

api_call "metrics" GET "${API_BASE}/metrics" "" no >/dev/null 2>&1 || true

NOW_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
FORECAST_REQ="$TMP_DIR/forecast.json"
cat > "$FORECAST_REQ" <<JSON
{
  "market_id": "${MARKET_ID}",
  "as_of_ts": "${NOW_UTC}",
  "freq": "5m",
  "horizon_steps": 6,
  "quantiles": [0.1, 0.5, 0.9],
  "y": [0.46, 0.47, 0.49, 0.48, 0.5, 0.52, 0.53, 0.51, 0.5, 0.54, 0.56, 0.55],
  "x_past": {
    "volume": [12, 13, 15, 14, 16, 18, 17, 16, 19, 20, 22, 21]
  },
  "x_future": {
    "volume": [22, 23, 24, 24, 25, 26]
  },
  "liquidity_bucket": "mid"
}
JSON

COMPARISON_REQ="$TMP_DIR/comparison.json"
cat > "$COMPARISON_REQ" <<JSON
{
  "forecast": $(cat "$FORECAST_REQ"),
  "baseline_liquidity_bucket": "low"
}
JSON

api_call "comparison" POST "${API_BASE}/markets/${MARKET_ID}/comparison" "$COMPARISON_REQ" no || true
COMPARISON_FILE="$API_CALL_OUT"
if [[ -n "$COMPARISON_FILE" && -s "$COMPARISON_FILE" ]]; then
  delta_q50="$(extract_json "$COMPARISON_FILE" "delta_last_q50" 2>/dev/null || echo "")"
  [[ -n "$delta_q50" ]] && KEY_LINES+=("- comparison.delta_last_q50: ${delta_q50}")
fi

api_call "tsfm_forecast_auth" POST "${API_BASE}/tsfm/forecast" "$FORECAST_REQ" yes || true
TSFM_FILE="$API_CALL_OUT"
if [[ -n "$TSFM_FILE" && -s "$TSFM_FILE" ]]; then
  q50_last="$(python3 - "$TSFM_FILE" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)
series = ((data.get('yhat_q') or {}).get('0.5') or [])
print(series[-1] if series else '')
PY
)"
  KEY_LINES+=("- tsfm_forecast.q50_last: ${q50_last:-N/A}")
fi

if (( FAIL_COUNT == 0 )); then
  FINAL_STATUS="PASS"
  EXIT_CODE=0
else
  FINAL_STATUS="FAIL"
  EXIT_CODE=1
fi

printf "\n=== Summary ===\n"
printf "Result: %s | Passed: %d/%d | Failed: %d\n" "$FINAL_STATUS" "$PASS_COUNT" "$TOTAL_COUNT" "$FAIL_COUNT"
printf "\nKey Fields:\n"
for line in "${KEY_LINES[@]}"; do
  printf "%s\n" "$line"
done

{
  printf "# Live Demo Smoke Report\n\n"
  printf -- "- Timestamp (UTC): %s\n" "$(date -u +"%Y-%m-%d %H:%M:%S")"
  printf -- "- API Base: %s\n" "$API_BASE"
  printf -- "- Final Result: **%s**\n" "$FINAL_STATUS"
  printf -- "- Passed: %d/%d\n" "$PASS_COUNT" "$TOTAL_COUNT"
  printf -- "- Failed: %d\n\n" "$FAIL_COUNT"

  printf "## Endpoint Checks\n"
  for line in "${SUMMARY_LINES[@]}"; do
    printf "%s\n" "$line"
  done

  printf "\n## Key Fields\n"
  if (( ${#KEY_LINES[@]} == 0 )); then
    printf -- "- N/A\n"
  else
    for line in "${KEY_LINES[@]}"; do
      printf "%s\n" "$line"
    done
  fi
} > "$REPORT_PATH"

printf "\nReport written: %s\n" "$REPORT_PATH"
exit "$EXIT_CODE"
