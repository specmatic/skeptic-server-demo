#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server

sleep 5
run_request -sS -D "$STATE/status-after.headers" -o "$STATE/status-after.json" "$SERVER_URL/status"
head -n 1 "$STATE/status-after.headers"
python3 -m json.tool "$STATE/status-after.json"
