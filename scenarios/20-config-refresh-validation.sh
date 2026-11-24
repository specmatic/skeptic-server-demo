#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
require_server
python3 "$ROOT/demo.py" token good
python3 "$ROOT/demo.py" prepare-request lint-config-refresh config-refresh-response 200
