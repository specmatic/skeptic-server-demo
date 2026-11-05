#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

run_request -sS -D "$STATE/status-before.headers" -o "$STATE/status-before.json" "$SERVER_URL/status"
head -n 1 "$STATE/status-before.headers"
python3 -m json.tool "$STATE/status-before.json"
