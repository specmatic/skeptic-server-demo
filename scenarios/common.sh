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
