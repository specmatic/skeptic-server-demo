#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server
SPEC_FILE="$ROOT/specs/large-openapi-over-25mb.yaml"
[[ "$(wc -c < "$SPEC_FILE" | tr -d ' ')" == 26214401 ]] || { echo "Expected a 26,214,401-byte fixture" >&2; exit 1; }
python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-request lint-over-25mb-spec
REQUEST_FILE="$STATE/lint-over-25mb-spec-authenticated.json"
RESPONSE_FILE="$STATE/lint-over-25mb-spec-response.json"
HTTP_STATUS=$(PRINT_REQUEST_BODY=0 run_request -sS --max-time 300 -w '%{http_code}' -o "$RESPONSE_FILE" \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" "$SERVER_URL/skeptic/lint/reports" | tee "$STATE/lint-over-25mb-spec-request.log" | tail -c 3)
echo "HTTP $HTTP_STATUS"
[[ "$HTTP_STATUS" == 422 ]] || { cat "$RESPONSE_FILE"; exit 1; }
python3 "$ROOT/demo.py" assert-error "$RESPONSE_FILE" SPEC_TOO_LARGE
