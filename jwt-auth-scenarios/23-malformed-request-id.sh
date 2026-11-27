#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
run_jwt_case bad-signature 400 INVALID_REQUEST malformed
