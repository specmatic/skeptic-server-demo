#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-request lint-large-spec
REQUEST_FILE="$STATE/lint-large-spec-authenticated.json"
run_request -sS -w '\nHTTP %{http_code}\n' \
  -o "$STATE/lint-large-response.json" \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports"
python3 "$ROOT/demo.py" summary "$STATE/lint-large-response.json" "Large 5MB spec lint"
