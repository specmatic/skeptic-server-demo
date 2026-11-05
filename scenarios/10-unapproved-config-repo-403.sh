#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

python3 "$ROOT/demo.py" token good
REQUEST_FILE="$ROOT/requests/lint-unapproved-config-repo.json"
run_request -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports"
