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
python3 "$ROOT/demo.py" prepare-request lint-25mb-spec lint-25mb-spec-response 200
