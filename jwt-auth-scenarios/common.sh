#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../scenarios/common.sh"

run_jwt_case() {
  local scenario="$1" expected_status="$2" expected_code="$3" id_mode="${4:-supplied}"
  local request_id token
  local -a args=(-sS --connect-timeout 3 --max-time 20)
  require_server
  printf 'Scenario: %s\nExpected: HTTP %s, JSON code=%s; nonempty message; UUID requestId matching X-Request-Id; Cache-Control: no-store.\n' \
    "$scenario" "$expected_status" "$expected_code"

  case "$id_mode" in
    supplied)
      request_id="${DEMO_REQUEST_ID:-$(new_request_id)}"
      args+=(-H "X-Request-Id: $request_id")
      printf 'Expected response requestId: %s\n' "$request_id"
      ;;
    malformed) args+=(-H 'X-Request-Id: not-a-uuid') ;;
    generated) ;; # Omit request ID so the server must generate one.
    *) echo "Unknown request ID mode: $id_mode" >&2; exit 2 ;;
  esac

  if [[ -n "${JWT_AUTH_RESULTS_DIR:-}" ]]; then
    mkdir -p "$JWT_AUTH_RESULTS_DIR"
    printf '%s' "${request_id:-}" > "$JWT_AUTH_RESULTS_DIR/request-id"
    args+=(--dump-header "$JWT_AUTH_RESULTS_DIR/headers.txt" --output "$JWT_AUTH_RESULTS_DIR/body.json")
  else
    args+=(-i)
  fi

  case "$scenario" in
    no-token) ;;
    empty-bearer) args+=(-H 'Authorization: Bearer') ;;
    basic-auth) args+=(-H 'Authorization: Basic dXNlcjpwYXNz') ;;
    malformed-header) args+=(-H 'Authorization: Bearer token extra') ;;
    *)
      token="$(python3 "$ROOT/jwt-auth-scenarios/token.py" "$scenario")"
      args+=(-H "Authorization: Bearer $token")
      ;;
  esac

  if [[ "$scenario" == valid ]]; then
    # Passing auth reaches Content-Type validation; no config access or report submission.
    args+=(-H 'Content-Type:' --data-binary "@$REQUEST_FILE")
  else
    args+=(-H 'Content-Type: application/json' --data-binary "@$REQUEST_FILE")
  fi
  run_request "${args[@]}" "$SERVER_URL/skeptic/lint/reports"
  printf '\n'
}
