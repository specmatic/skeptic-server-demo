#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE="$ROOT/.demo-state"
SESSION="$STATE/session-$(date +%Y%m%d-%H%M%S)-$$"
FIXTURE_URL="http://127.0.0.1:8765"
CONTAINER_FIXTURE_URL="http://host.docker.internal:8765"
SERVER_PORT=8000
SERVER_URL="http://127.0.0.1:$SERVER_PORT"
TLS_DIR="$SESSION/tls"
ENTERPRISE_IMAGE="${SPECMATIC_ENTERPRISE_IMAGE:-specmatic/enterprise:latest}"
CONTAINER_NAME="skeptic-lint-demo-$$"

if [[ "${1:-}" != "start" || $# -gt 2 || ( $# -eq 2 && "$2" != "--https" ) ]]; then
  echo "Usage: ./demo.sh start [--https]" >&2
  exit 2
fi
if [[ "${2:-}" == "--https" ]]; then
  SERVER_PORT=8443
  SERVER_URL="https://localhost:$SERVER_PORT"
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run the lint server." >&2
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
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
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
  docker run --rm --name "$CONTAINER_NAME"
  --publish "127.0.0.1:$SERVER_PORT:$SERVER_PORT"
  --mount "type=bind,source=$SESSION,target=/demo"
  --workdir /demo
)
# Docker Desktop provides this DNS name; native Docker Engine needs a mapping.
if [[ "$(docker info --format '{{.OperatingSystem}}')" != *"Docker Desktop"* ]]; then
  SERVER_COMMAND+=(--add-host host.docker.internal:host-gateway)
fi
if [[ -n "${SPECMATIC_LICENSE_CONTENT:-}" ]]; then
  SERVER_COMMAND+=(--env SPECMATIC_LICENSE_CONTENT)
elif [[ -n "${SPECMATIC_LICENSE_PATH:-}" || -f "$HOME/.specmatic/specmatic-license.txt" ]]; then
  LICENSE_FILE="${SPECMATIC_LICENSE_PATH:-$HOME/.specmatic/specmatic-license.txt}"
  SERVER_COMMAND+=(
    --mount "type=bind,source=$LICENSE_FILE,target=/specmatic-license.txt,readonly"
    --env SPECMATIC_LICENSE_PATH=/specmatic-license.txt
  )
fi
if [[ "${2:-}" == "--https" ]]; then
  SERVER_COMMAND+=(--env SPECMATIC_TLS_KEYSTORE_PASSWORD --env SPECMATIC_TLS_PRIVATE_KEY_PASSWORD)
fi
SERVER_COMMAND+=(
  "$ENTERPRISE_IMAGE" lint-server
  --port="$SERVER_PORT"
  --jwt-issuer="$FIXTURE_URL/demo-issuer"
  --jwt-jwks-url="$CONTAINER_FIXTURE_URL/jwks.json"
  --jwt-audience=skeptic-lint-demo
  --jwt-match='scope="lint:run reports:read"'
  --allowed-config-repo-url="https://github.com/specmatic/private-central-linter-config.git"
  --allowed-spec-download-host=host.docker.internal
)
if [[ "${2:-}" == "--https" ]]; then
  SERVER_COMMAND+=(--tls-keystore=/demo/tls/server.p12 --tls-key-alias=lint-server)
fi
{
  printf 'Running command:'
  printf ' %q' "${SERVER_COMMAND[@]}"
  printf '\n'
  "${SERVER_COMMAND[@]}"
} 2>&1 | tee "$STATE/server.log"
