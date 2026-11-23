#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server
SPEC_FILE="$ROOT/specs/large-openapi-over-25mb.yaml"
[[ "$(wc -c < "$SPEC_FILE" | tr -d ' ')" == 26214401 ]] || { echo "Expected a 26,214,401-byte fixture" >&2; exit 1; }
python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-request lint-over-25mb-spec lint-over-25mb-spec-response 422
python3 "$ROOT/demo.py" assert-error "$STATE/lint-over-25mb-spec-response.json" SPEC_TOO_LARGE
