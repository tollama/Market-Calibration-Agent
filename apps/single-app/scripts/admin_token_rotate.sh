#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/admin_token_rotate.sh [--env-file <path>] [--bytes <n>] [--print-only]

Options:
  --env-file <path>  Update ADMIN_API_TOKEN in this env file (default: .env)
  --bytes <n>        Random byte length before hex encoding (default: 32)
  --print-only       Print token only, do not modify env file

Examples:
  scripts/admin_token_rotate.sh
  scripts/admin_token_rotate.sh --env-file .env --bytes 48
  scripts/admin_token_rotate.sh --print-only
EOF
}

ENV_FILE=".env"
BYTES="32"
PRINT_ONLY="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --bytes)
      BYTES="$2"
      shift 2
      ;;
    --print-only)
      PRINT_ONLY="true"
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! [[ "$BYTES" =~ ^[0-9]+$ ]] || [[ "$BYTES" -lt 16 ]]; then
  echo "--bytes must be an integer >= 16" >&2
  exit 1
fi

NEW_TOKEN="$(node -e "console.log(require('crypto').randomBytes(${BYTES}).toString('hex'))")"

if [[ "$PRINT_ONLY" == "true" ]]; then
  echo "$NEW_TOKEN"
  exit 0
fi

mkdir -p "$(dirname "$ENV_FILE")"
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^ADMIN_API_TOKEN=' "$ENV_FILE"; then
  awk -v token="$NEW_TOKEN" '
    BEGIN { updated = 0 }
    /^ADMIN_API_TOKEN=/ {
      print "ADMIN_API_TOKEN=\"" token "\""
      updated = 1
      next
    }
    { print }
    END {
      if (updated == 0) {
        print "ADMIN_API_TOKEN=\"" token "\""
      }
    }
  ' "$ENV_FILE" >"${ENV_FILE}.tmp"
  mv "${ENV_FILE}.tmp" "$ENV_FILE"
else
  {
    [[ -f "$ENV_FILE" ]] && cat "$ENV_FILE"
    [[ -f "$ENV_FILE" ]] && echo
    echo "ADMIN_API_TOKEN=\"$NEW_TOKEN\""
  } >"$ENV_FILE"
fi

MASKED="${NEW_TOKEN:0:4}****${NEW_TOKEN: -4}"
echo "[OK] ADMIN_API_TOKEN rotated: $MASKED"
echo "[OK] Updated env file: $ENV_FILE"
echo
cat <<EOF
Next steps:
1) Reload env and restart app/worker
   set -a; source $ENV_FILE; set +a
   npm run dev
   npm run worker
2) Re-validate auth + execution flow
   ADMIN_API_TOKEN=\"\$ADMIN_API_TOKEN\" npm run smoke:ci
EOF
