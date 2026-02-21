#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
API_BASE="${API_BASE:-http://${API_HOST}:${API_PORT}}"
if [[ -x ".venv311/bin/python" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-.venv311/bin/python}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3.11}"
fi
TSFM_TOKEN="${TSFM_FORECAST_API_TOKEN:-tsfm-dev-token}"
REPORT_PATH="${REPORT_PATH:-artifacts/demo/live_demo_security_check.md}"
AUTO_START_API="${AUTO_START_API:-1}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required" >&2
  exit 1
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} not found (set PYTHON_BIN)" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  if [[ -n "${API_PID:-}" ]]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PAYLOAD_JSON="$TMP_DIR/payload.json"
export PAYLOAD_JSON
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path
fixture = Path("tests/fixtures/prd2/D1_normal.json")
obj = json.loads(fixture.read_text(encoding="utf-8"))
Path(os.environ["PAYLOAD_JSON"]).write_text(json.dumps(obj["request"]), encoding="utf-8")
PY

if [[ "$AUTO_START_API" == "1" ]]; then
  if ! "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1; then
    echo "AUTO_START_API=1 but uvicorn is unavailable for $PYTHON_BIN. Set PYTHON_BIN to an env with uvicorn, or run API separately and use AUTO_START_API=0." >&2
    exit 1
  fi
  "$PYTHON_BIN" -m uvicorn api.app:app --host "$API_HOST" --port "$API_PORT" >/tmp/live_demo_security_uvicorn.log 2>&1 &
  API_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sS "$API_BASE/metrics" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -sS "$API_BASE/metrics" >/dev/null 2>&1; then
  echo "API not reachable at $API_BASE. Start the API or set AUTO_START_API=1 with uvicorn available." >&2
  [[ -f /tmp/live_demo_security_uvicorn.log ]] && tail -n 20 /tmp/live_demo_security_uvicorn.log >&2 || true
  exit 1
fi

TS_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# 1) Unauthorized check -> 401
UNAUTH_HEADERS="$TMP_DIR/unauth.headers"
UNAUTH_BODY="$TMP_DIR/unauth.body"
UNAUTH_CODE="$(curl -sS -o "$UNAUTH_BODY" -D "$UNAUTH_HEADERS" -w "%{http_code}" \
  -X POST "$API_BASE/tsfm/forecast" \
  -H "Content-Type: application/json" \
  --data @"$PAYLOAD_JSON")"

# 2) Valid token happy path -> 200
HAPPY_HEADERS="$TMP_DIR/happy.headers"
HAPPY_BODY="$TMP_DIR/happy.body"
HAPPY_CODE="$(curl -sS -o "$HAPPY_BODY" -D "$HAPPY_HEADERS" -w "%{http_code}" \
  -X POST "$API_BASE/tsfm/forecast" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TSFM_TOKEN" \
  --data @"$PAYLOAD_JSON")"

# 3) Rate-limit burst -> expect at least one 429 + Retry-After header
RATE_LIMITED_CODE=""
RETRY_AFTER=""
for i in 1 2 3 4 5 6 7 8; do
  H="$TMP_DIR/rate_${i}.headers"
  B="$TMP_DIR/rate_${i}.body"
  C="$(curl -sS -o "$B" -D "$H" -w "%{http_code}" \
    -X POST "$API_BASE/tsfm/forecast" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TSFM_TOKEN" \
    --data @"$PAYLOAD_JSON")"
  if [[ "$C" == "429" ]]; then
    RATE_LIMITED_CODE="$C"
    RETRY_AFTER="$(awk -F': ' 'tolower($1)=="retry-after" {gsub(/\r/, "", $2); print $2}' "$H" | tail -n1)"
    break
  fi
done

HAPPY_SUMMARY="$TMP_DIR/happy_summary.txt"
export HAPPY_BODY HAPPY_SUMMARY
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path
p = Path(os.environ["HAPPY_BODY"])
out = Path(os.environ["HAPPY_SUMMARY"])
try:
    obj = json.loads(p.read_text(encoding="utf-8"))
    q50 = obj.get("yhat_q", {}).get("0.5")
    meta = obj.get("meta", {})
    out.write_text(
        json.dumps(
            {
                "market_id": obj.get("market_id"),
                "q50_len": len(q50) if isinstance(q50, list) else None,
                "runtime": meta.get("runtime"),
                "fallback_used": meta.get("fallback_used"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
except Exception as e:
    out.write_text(json.dumps({"parse_error": str(e)}), encoding="utf-8")
PY

HAPPY_JSON="$(cat "$HAPPY_SUMMARY")"
mkdir -p "$(dirname "$REPORT_PATH")"
cat >"$REPORT_PATH" <<EOF
# Live Demo Security Validation Check

- Executed at (UTC): ${TS_UTC}
- API base: ${API_BASE}
- Script: scripts/live_demo_security_check.sh

## Results

| Check | Expected | Observed | Status |
|---|---:|---:|---|
| Unauthorized request to POST /tsfm/forecast | 401 | ${UNAUTH_CODE} | $( [[ "$UNAUTH_CODE" == "401" ]] && echo "PASS" || echo "FAIL" ) |
| Valid token happy path | 200 | ${HAPPY_CODE} | $( [[ "$HAPPY_CODE" == "200" ]] && echo "PASS" || echo "FAIL" ) |
| Burst rate limit | 429 + Retry-After | ${RATE_LIMITED_CODE:-none} + ${RETRY_AFTER:-missing} | $( [[ "${RATE_LIMITED_CODE:-}" == "429" && -n "${RETRY_AFTER:-}" ]] && echo "PASS" || echo "FAIL" ) |

## Happy Path Response Summary

~~~json
${HAPPY_JSON}
~~~

## Public Demo Safe Guidance

- Use a non-production demo token only; rotate it after the session.
- Never display raw secrets on screen (terminal history, env dumps, CI logs).
- Keep auth enabled for demo API endpoints; do not disable require_auth.
- Keep rate-limit protection enabled to prevent accidental burst abuse during live Q&A.
- If a check fails, stop the public demo and fix configuration before continuing.
- Share only status codes and high-level behavior publicly; avoid exposing internals (stack traces, private endpoints, infrastructure details).

## Repro Command

~~~bash
scripts/live_demo_security_check.sh
~~~
EOF

echo "Wrote report: $REPORT_PATH"
echo "Unauthorized=${UNAUTH_CODE}, HappyPath=${HAPPY_CODE}, RateLimited=${RATE_LIMITED_CODE:-none}, Retry-After=${RETRY_AFTER:-missing}"