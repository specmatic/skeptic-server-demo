#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

python3 "$ROOT/demo.py" token good
echo "POST /skeptic/lint/reports request:"
cat "$REQUEST_FILE"
echo
curl -sS -w '\nHTTP %{http_code}\n' \
  -o "$STATE/lint-response.json" \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports"
python3 "$ROOT/demo.py" summary "$STATE/lint-response.json" "Batch lint"
