#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

submit_lint_fixture lint-unknown-profile "$(new_request_id)" -i
