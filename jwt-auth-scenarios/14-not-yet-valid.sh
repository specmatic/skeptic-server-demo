#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
run_jwt_case not-yet-valid 401 INVALID_TOKEN
