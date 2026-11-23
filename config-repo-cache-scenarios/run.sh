#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-help}"

require_repo_url() {
  if [[ -z "${DEMO_CONFIG_REPO_URL:-}" ]]; then
    echo "Set DEMO_CONFIG_REPO_URL to the credential-free config repository URL." >&2
    exit 2
  fi
}

case "$ACTION" in
  start)
    require_repo_url
    DEMO_ALLOWED_CONFIG_REPO_URL="${DEMO_ALLOWED_CONFIG_REPO_URL:-$DEMO_CONFIG_REPO_URL}"
    export DEMO_ALLOWED_CONFIG_REPO_URL
    shift
    exec "$ROOT/demo.sh" start "$@"
    ;;
  lint)
    require_repo_url
    if [[ -z "${DEMO_CONFIG_TOKEN:-}" && "${DEMO_NO_CONFIG_TOKEN:-0}" != 1 ]]; then
      echo "Set DEMO_CONFIG_TOKEN from the approved App-token broker; use DEMO_NO_CONFIG_TOKEN=1 for public repos." >&2
      exit 2
    fi
    exec "$ROOT/scenarios/20-config-refresh-validation.sh"
    ;;
  status)
    exec "$ROOT/scenarios/07-status-after-lint.sh"
    ;;
  wait)
    if [[ -z "${2:-}" ]]; then
      echo "Usage: $0 wait <full-commit-sha>" >&2
      exit 2
    fi
    exec python3 "$ROOT/scripts/wait_config_refresh.py" --sha "$2"
    ;;
  verify)
    if [[ -z "${2:-}" ]]; then
      echo "Usage: $0 verify <full-commit-sha>" >&2
      exit 2
    fi
    exec python3 "$ROOT/demo.py" assert-refresh "$ROOT/.demo-state/config-refresh-response.json" "$2"
    ;;
  local-smoke)
    exec python3 -B "$ROOT/scripts/validate_config_refresh_local.py" --smoke
    ;;
  local-full)
    exec python3 -B "$ROOT/scripts/validate_config_refresh_local.py"
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: config-repo-cache-scenarios/run.sh <command>

  start [--https]  Start demo server; DEMO_CONFIG_REPO_URL sets exact allowlist URL.
  lint             Submit marker-spec lint with DEMO_CONFIG_TOKEN in config.git.token.
  status           Show /status once.
  wait <sha>        Poll /status only until SHA is fresh.
  verify <sha>      Assert response SHA and CLIENT_VALIDATION_C1 SARIF marker.
  local-smoke       Run controlled Git HTTP checks; skip scheduler timing.
  local-full        Run controlled Git HTTP checks through five-minute refresh.
EOF
    ;;
  *)
    echo "Unknown command: $ACTION" >&2
    exit 2
    ;;
esac
