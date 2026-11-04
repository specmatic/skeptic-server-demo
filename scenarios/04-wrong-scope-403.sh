#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

python3 "$ROOT/demo.py" token bad
curl -sS -i \
  -H "Authorization: Bearer $(cat "$STATE/bad.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports"
