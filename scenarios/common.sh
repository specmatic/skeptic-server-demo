#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.demo-state"
SERVER_URL="http://127.0.0.1:8000"
REQUEST_FILE="$ROOT/requests/lint-batch.json"

require_server() {
  if ! nc -z -w 1 127.0.0.1 8000 >/dev/null 2>&1; then
    echo "Start the lint server first: ./demo.sh start" >&2
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
  curl "${args[@]}"
}
