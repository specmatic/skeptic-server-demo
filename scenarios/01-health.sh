#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server
run_request -sS -i "$SERVER_URL/health"
