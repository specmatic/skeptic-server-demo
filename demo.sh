#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE="$ROOT/.demo-state"
SESSION="$STATE/session-$(date +%Y%m%d-%H%M%S)-$$"
FIXTURE_URL="http://127.0.0.1:8765"
SERVER_PORT=8000
SERVER_URL="http://127.0.0.1:$SERVER_PORT"
TLS_DIR="$SESSION/tls"
ENTERPRISE_ROOT="$ROOT/../enterprise"
ENTERPRISE_JAR="$ENTERPRISE_ROOT/executable/build/libs/executable-1.28.4-all-obfuscated.jar"

if [[ "${1:-}" != "start" || $# -gt 2 || ( $# -eq 2 && "$2" != "--https" ) ]]; then
  echo "Usage: ./demo.sh start [--https]" >&2
  exit 2
fi
if [[ "${2:-}" == "--https" ]]; then
  SERVER_PORT=8443
  SERVER_URL="https://localhost:$SERVER_PORT"
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
if [[ "${2:-}" == "--https" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "OpenSSL is required to create the local HTTPS certificate." >&2
    exit 1
  fi

  mkdir -p "$TLS_DIR"
  chmod 700 "$TLS_DIR"
  TLS_KEYSTORE_PASSWORD="$(openssl rand -hex 24)"
  export SPECMATIC_TLS_KEYSTORE_PASSWORD="$TLS_KEYSTORE_PASSWORD"
  export SPECMATIC_TLS_PRIVATE_KEY_PASSWORD="$TLS_KEYSTORE_PASSWORD"
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 \
    -keyout "$TLS_DIR/server.key" \
    -out "$TLS_DIR/server.crt" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
  openssl pkcs12 -export \
    -out "$TLS_DIR/server.p12" \
    -inkey "$TLS_DIR/server.key" \
    -in "$TLS_DIR/server.crt" \
    -name lint-server \
    -passout env:SPECMATIC_TLS_KEYSTORE_PASSWORD
  rm "$TLS_DIR/server.key"
  chmod 600 "$TLS_DIR/server.p12"
  printf '%s\n' "$TLS_DIR/server.crt" > "$STATE/server-ca"
else
  rm -f "$STATE/server-ca"
fi
printf '%s\n' "$SERVER_URL" > "$STATE/server-url"
printf '%s\n' "$SERVER_PORT" > "$STATE/server-port"
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

echo "Starting the lint server on $SERVER_URL"
echo "Run one scenario at a time from a second terminal. Press Ctrl-C here when done."
cd "$SESSION"
SERVER_COMMAND=(
  java -jar "$ENTERPRISE_JAR" lint-server
  --port="$SERVER_PORT"
  --jwt-issuer="$FIXTURE_URL/demo-issuer"
  --jwt-jwks-url="$FIXTURE_URL/jwks.json"
  --jwt-audience=skeptic-lint-demo
  --jwt-match='scope="lint:run reports:read"'
  --allowed-config-repo-url="https://github.com/specmatic/private-central-linter-config.git"
  --allowed-spec-download-host=127.0.0.1
)
if [[ "${2:-}" == "--https" ]]; then
  SERVER_COMMAND+=(--tls-keystore="$TLS_DIR/server.p12" --tls-key-alias=lint-server)
fi
{
  printf 'Running command:'
  printf ' %q' "${SERVER_COMMAND[@]}"
  printf '\n'
  "${SERVER_COMMAND[@]}"
} 2>&1 | tee "$STATE/server.log"
