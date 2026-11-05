#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE="$ROOT/.demo-state"
SESSION="$STATE/session-$(date +%Y%m%d-%H%M%S)-$$"
FIXTURE_URL="http://127.0.0.1:8765"
SERVER_PORT=8000
ENTERPRISE_ROOT="$ROOT/../enterprise"
ENTERPRISE_JAR="$ENTERPRISE_ROOT/executable/build/libs/executable-1.28.4-all-obfuscated.jar"

if [[ "${1:-}" != "start" || $# -ne 1 ]]; then
  echo "Usage: ./demo.sh start" >&2
  exit 2
fi

if [[ ! -f "$ENTERPRISE_JAR" ]]; then
  echo "Enterprise jar not found: $ENTERPRISE_JAR" >&2
  echo "Build it with: (cd \"$ENTERPRISE_ROOT\" && ./gradlew :executable:shadowObfuscatedJar)" >&2
  exit 1
fi
if [[ -n "${SPECMATIC_LICENSE_PATH:-}" && ! -f "$SPECMATIC_LICENSE_PATH" ]]; then
  echo "SPECMATIC_LICENSE_PATH does not point to a file." >&2
  exit 1
fi
if [[ -n "${SPECMATIC_LICENSE_PATH:-}" ]]; then
  LICENSE_DIR="$(cd "$(dirname "$SPECMATIC_LICENSE_PATH")" && pwd)"
  export SPECMATIC_LICENSE_PATH="$LICENSE_DIR/$(basename "$SPECMATIC_LICENSE_PATH")"
fi

mkdir -p "$STATE"
mkdir -p "$SESSION"
python3 "$ROOT/fixture_server.py" prepare
DEMO_FIXTURE_PORT=8765 python3 "$ROOT/fixture_server.py" >"$STATE/fixtures.log" 2>&1 &
FIXTURE_PID=$!
stop_fixtures() {
  kill "$FIXTURE_PID" 2>/dev/null || true
  wait "$FIXTURE_PID" 2>/dev/null || true
}
trap stop_fixtures EXIT INT TERM

for _ in {1..40}; do
  if curl -fsS "$FIXTURE_URL/jwks.json" >/dev/null 2>&1; then break; fi
  sleep 0.25
done
if ! curl -fsS "$FIXTURE_URL/jwks.json" >/dev/null 2>&1; then
  echo "Demo fixture server did not start. See .demo-state/fixtures.log" >&2
  exit 1
fi

echo "Starting the lint server on http://localhost:$SERVER_PORT"
echo "Run one scenario at a time from a second terminal. Press Ctrl-C here when done."
cd "$SESSION"
java -jar "$ENTERPRISE_JAR" lint-server \
  --port="$SERVER_PORT" \
  --jwt-issuer="$FIXTURE_URL/demo-issuer" \
  --jwt-jwks-url="$FIXTURE_URL/jwks.json" \
  --jwt-audience=cba-lint-demo \
  --jwt-match='scope="lint:run reports:read"' \
  --allowed-config-repo-url="$FIXTURE_URL/config.git" \
  --allowed-spec-download-host=127.0.0.1 2>&1 | tee "$STATE/server.log"
