#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.demo-state"
SERVER_URL="$(cat "$STATE/server-url" 2>/dev/null || printf 'http://127.0.0.1:8000')"
SERVER_PORT="$(cat "$STATE/server-port" 2>/dev/null || printf '8000')"
SERVER_CA_FILE="$(cat "$STATE/server-ca" 2>/dev/null || true)"
REQUEST_FILE="$ROOT/requests/lint-batch.json"

require_server() {
  if ! nc -z -w 1 127.0.0.1 "$SERVER_PORT" >/dev/null 2>&1; then
    echo "Start the lint server first: ./demo.sh start [--https]" >&2
    exit 1
  fi
}

new_request_id() {
  python3 -c 'import uuid; print(uuid.uuid4())'
}

# Display the request alongside curl's existing response output.
run_request() {
  local method=GET url="" body_file="" header
  local -a headers=() args=("$@")
  while (( $# )); do
    case "$1" in
      -H)
        header="$2"
        headers+=("$header")
        shift 2
        ;;
      --data-binary)
        method=POST
        body_file="${2#@}"
        shift 2
        ;;
      http://*|https://*) url="$1"; shift ;;
      *) shift ;;
    esac
  done

  printf '\n=== Request ===\n%s %s\n' "$method" "$url"
  for header in ${headers[@]+"${headers[@]}"}; do
    printf '%s\n' "$header"
  done
  if [[ -n "$body_file" ]]; then
    printf '\n'
    cat "$body_file"
    printf '\n'
  fi
  printf '\n=== Response ===\n'
  local -a curl_args=("${args[@]}")
  if [[ -n "$SERVER_CA_FILE" ]]; then
    curl_args+=(--cacert "$SERVER_CA_FILE")
  fi
  curl "${curl_args[@]}"
}

submit_lint_fixture() {
  local request_name="$1" request_id="$2"
  shift 2
  require_server
  python3 "$ROOT/demo.py" token good
  python3 "$ROOT/demo.py" prepare-request "$request_name"
  run_request -sS \
    -H "Authorization: Bearer $(cat "$STATE/good.jwt")" \
    -H 'Content-Type: application/json' \
    -H "X-Request-Id: $request_id" \
    --data-binary "@$STATE/$request_name-authenticated.json" \
    "$@" "$SERVER_URL/skeptic/lint/reports"
}
