#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_URL="${APP_URL:-http://127.0.0.1:3000}"
HEALTH_URL="${APP_URL}/api/health"
START_URL="${APP_URL}/api/execution/start"
STOP_URL="${APP_URL}/api/execution/stop"
LOG_FILE="${ROOT_DIR}/.ci_smoke.dev.log"

PASS_COUNT=0
FAIL_COUNT=0
DEV_SERVER_PID=""
TOKEN_FROM_ENV=false

mask_token() {
  local token="$1"
  local len=${#token}
  if (( len <= 8 )); then
    printf '****'
  else
    printf '%s****%s' "${token:0:4}" "${token: -4}"
  fi
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "[PASS] $1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "[FAIL] $1"
}

cleanup() {
  if [[ -n "$DEV_SERVER_PID" ]] && kill -0 "$DEV_SERVER_PID" >/dev/null 2>&1; then
    kill "$DEV_SERVER_PID" >/dev/null 2>&1 || true
    wait "$DEV_SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

http_call() {
  local method="$1"
  local url="$2"
  local body="${3:-}"
  local auth_token="${4:-}"

  local output_file
  output_file="$(mktemp)"
  local code

  if [[ -n "$auth_token" ]]; then
    if [[ -n "$body" ]]; then
      code="$(curl -sS -o "$output_file" -w '%{http_code}' -X "$method" "$url" -H "Authorization: Bearer $auth_token" -H 'content-type: application/json' -d "$body")"
    else
      code="$(curl -sS -o "$output_file" -w '%{http_code}' -X "$method" "$url" -H "Authorization: Bearer $auth_token")"
    fi
  else
    if [[ -n "$body" ]]; then
      code="$(curl -sS -o "$output_file" -w '%{http_code}' -X "$method" "$url" -H 'content-type: application/json' -d "$body")"
    else
      code="$(curl -sS -o "$output_file" -w '%{http_code}' -X "$method" "$url")"
    fi
  fi

  HTTP_CODE="$code"
  HTTP_BODY_FILE="$output_file"
}

json_eval() {
  local file="$1"
  local expr="$2"
  node -e '
    const fs = require("fs");
    const file = process.argv[1];
    const expr = process.argv[2];
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    let value;
    try {
      value = Function("data", `return (${expr});`)(data);
    } catch (_) {
      process.exit(2);
    }
    if (value === true) process.exit(0);
    process.exit(1);
  ' "$file" "$expr"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "필수 명령어가 없습니다: $1" >&2
    exit 1
  }
}

require_cmd docker
require_cmd curl
require_cmd npm
require_cmd node

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/market_calibration?schema=public}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"

if [[ -n "${ADMIN_API_TOKEN:-}" ]]; then
  TOKEN_FROM_ENV=true
else
  ADMIN_API_TOKEN="$(node -e 'console.log(require("crypto").randomBytes(24).toString("hex"))')"
fi
export ADMIN_API_TOKEN

echo "[INFO] ADMIN_API_TOKEN: $(mask_token "$ADMIN_API_TOKEN") (source=$([[ "$TOKEN_FROM_ENV" == true ]] && echo env || echo generated))"

echo "[INFO] Starting postgres/redis (docker compose, reuse if already running)"
docker compose up -d postgres redis >/dev/null

# Wait postgres ready
for i in {1..60}; do
  if docker exec single-app-postgres pg_isready -U postgres >/dev/null 2>&1; then
    pass "Postgres ready"
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    fail "Postgres readiness timeout"
    exit 1
  fi
  sleep 1
done

# Wait redis ready
for i in {1..60}; do
  if docker exec single-app-redis redis-cli ping 2>/dev/null | grep -q PONG; then
    pass "Redis ready"
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    fail "Redis readiness timeout"
    exit 1
  fi
  sleep 1
done

echo "[INFO] Running DB migrate (prisma migrate deploy)"
npx prisma migrate deploy >/tmp/ci_smoke_migrate.log 2>&1 || {
  echo "[FAIL] DB migrate failed"
  cat /tmp/ci_smoke_migrate.log
  exit 1
}
pass "DB migrate"

echo "[INFO] Starting dev server in background"
: > "$LOG_FILE"
npm run dev >"$LOG_FILE" 2>&1 &
DEV_SERVER_PID=$!

for i in {1..90}; do
  if curl -sS -o /dev/null "$HEALTH_URL"; then
    pass "Dev server ready"
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    fail "Dev server health wait timeout"
    tail -n 80 "$LOG_FILE" || true
    exit 1
  fi
  sleep 1
done

# Precondition: kill-switch OFF
http_call GET "$STOP_URL"
if [[ "$HTTP_CODE" == "200" ]] && json_eval "$HTTP_BODY_FILE" 'data.ok === true && data.killSwitch && data.killSwitch.enabled === true'; then
  rm -f "$HTTP_BODY_FILE"
  http_call POST "$STOP_URL" '{"enabled":false,"reason":"ci smoke precondition"}' "$ADMIN_API_TOKEN"
  if [[ "$HTTP_CODE" != "200" ]]; then
    fail "Precondition stop(false) failed (HTTP $HTTP_CODE)"
    cat "$HTTP_BODY_FILE"
    rm -f "$HTTP_BODY_FILE"
    exit 1
  fi
fi
rm -f "$HTTP_BODY_FILE"

# a) health 200 + db.ok=true
http_call GET "$HEALTH_URL"
if [[ "$HTTP_CODE" == "200" ]] && json_eval "$HTTP_BODY_FILE" 'data.ok === true && data.db && data.db.ok === true'; then
  pass "a) health 200 + db.ok=true"
else
  fail "a) health check failed (HTTP $HTTP_CODE)"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

# b) start without token => 401/403
http_call POST "$START_URL" '{"mode":"paper","dryRun":true,"maxPosition":1000}'
if [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
  pass "b) start without token => $HTTP_CODE"
else
  fail "b) expected 401/403, got $HTTP_CODE"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

# c) start with token => 202
http_call POST "$START_URL" '{"mode":"paper","dryRun":true,"maxPosition":1000}' "$ADMIN_API_TOKEN"
if [[ "$HTTP_CODE" == "202" ]]; then
  pass "c) start with token => 202"
else
  fail "c) expected 202, got $HTTP_CODE"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

# d) stop enabled=true => 200
http_call POST "$STOP_URL" '{"enabled":true,"reason":"ci smoke stop on"}' "$ADMIN_API_TOKEN"
if [[ "$HTTP_CODE" == "200" ]]; then
  pass "d) stop enabled=true => 200"
else
  fail "d) expected 200, got $HTTP_CODE"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

# e) start again => 409
http_call POST "$START_URL" '{"mode":"paper","dryRun":true,"maxPosition":1000}' "$ADMIN_API_TOKEN"
if [[ "$HTTP_CODE" == "409" ]]; then
  pass "e) start again => 409"
else
  fail "e) expected 409, got $HTTP_CODE"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

# f) stop enabled=false => 200
http_call POST "$STOP_URL" '{"enabled":false,"reason":"ci smoke reset"}' "$ADMIN_API_TOKEN"
if [[ "$HTTP_CODE" == "200" ]]; then
  pass "f) stop enabled=false => 200"
else
  fail "f) expected 200, got $HTTP_CODE"
  cat "$HTTP_BODY_FILE"
  rm -f "$HTTP_BODY_FILE"
  exit 1
fi
rm -f "$HTTP_BODY_FILE"

echo
if [[ "$FAIL_COUNT" -eq 0 ]]; then
  echo "[RESULT] Smoke test PASSED (${PASS_COUNT} checks)"
else
  echo "[RESULT] Smoke test FAILED (pass=${PASS_COUNT}, fail=${FAIL_COUNT})"
  exit 1
fi
