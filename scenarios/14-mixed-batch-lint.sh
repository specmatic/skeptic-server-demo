#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

submit_lint_fixture lint-mixed-batch "${DEMO_REQUEST_ID:-$(new_request_id)}" \
  -D "$STATE/lint-mixed-response.headers" \
  -o "$STATE/lint-mixed-response.json" \
  -w '\nHTTP %{http_code}\n'
cat "$STATE/lint-mixed-response.headers"
python3 "$ROOT/demo.py" summary "$STATE/lint-mixed-response.json" "Mixed batch lint"
