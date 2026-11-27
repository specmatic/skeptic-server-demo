#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
run_jwt_case no-token 401 AUTHENTICATION_REQUIRED
