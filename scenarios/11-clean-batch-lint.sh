#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-clean-request
REQUEST_FILE="$STATE/lint-clean-batch-authenticated.json"
run_request -sS -w '\nHTTP %{http_code}\n' \
  -o "$STATE/lint-clean-response.json" \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports"
python3 "$ROOT/demo.py" summary "$STATE/lint-clean-response.json" "Clean batch lint"
