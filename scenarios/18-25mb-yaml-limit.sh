#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

SPEC_FILE="$ROOT/specs/large-openapi-25mb.yaml"
[[ "$(wc -c < "$SPEC_FILE" | tr -d ' ')" == 26214400 ]] || {
  echo "Expected a 26,214,400-byte fixture: $SPEC_FILE" >&2
  exit 1
}
python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-request lint-25mb-spec
REQUEST_FILE="$STATE/lint-25mb-spec-authenticated.json"
RESPONSE_FILE="$STATE/lint-25mb-spec-response.json"
HTTP_STATUS=$(PRINT_REQUEST_BODY=0 run_request -sS --max-time 300 \
  -w '%{http_code}' -o "$RESPONSE_FILE" \
  -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(new_request_id)" \
  --data-binary "@$REQUEST_FILE" \
  "$SERVER_URL/skeptic/lint/reports" | tee "$STATE/lint-25mb-spec-request.log" | tail -c 3)
echo "HTTP $HTTP_STATUS"
if [[ "$HTTP_STATUS" != 200 ]]; then
  cat "$RESPONSE_FILE"
  exit 1
fi
python3 - "$RESPONSE_FILE" <<'PY'
import json
import sys

response = json.load(open(sys.argv[1]))
reports = response.get("reports", [])
assert len(reports) == 1, "Expected one lint report"
assert reports[0]["specId"] == "large-openapi-25mb", "Unexpected specification"
assert reports[0].get("sarifReport", {}).get("runs"), "Expected a SARIF lint report"
print("Verified: static 25 MiB YAML accepted and lint report returned.")
PY
python3 "$ROOT/demo.py" summary "$RESPONSE_FILE" "25 MiB YAML lint"
