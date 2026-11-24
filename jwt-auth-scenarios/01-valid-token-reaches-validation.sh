#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
run_jwt_case valid 415 UNSUPPORTED_MEDIA_TYPE
