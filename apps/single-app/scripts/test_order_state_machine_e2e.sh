#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[e2e] docker가 필요합니다." >&2
  exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "[e2e] npx가 필요합니다." >&2
  exit 1
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/market_calibration?schema=public}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
export ADMIN_API_TOKEN="${ADMIN_API_TOKEN:-test-admin-token}"

echo "[e2e] starting postgres/redis..."
docker compose up -d postgres redis >/dev/null

echo "[e2e] applying schema (prisma db push)..."
npx prisma db push --skip-generate >/dev/null

echo "[e2e] running order state-machine integration test..."
npm run test:e2e:order-sm
