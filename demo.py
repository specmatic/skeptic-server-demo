#!/usr/bin/env python3
"""Generate short-lived demo JWTs and print compact response summaries."""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".demo-state"
ISSUER = "http://127.0.0.1:8765/demo-issuer"


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def create_token(scope: str, destination: Path) -> None:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": "skeptic-demo-key"}
    claims = {
        "iss": ISSUER,
        "aud": "skeptic-lint-demo",
        "sub": "skeptic-demo-caller",
        "iat": now,
        "nbf": now - 5,
        "exp": now + 1800,
        "scope": scope,
    }
    unsigned = f"{b64url(json.dumps(header, separators=(',', ':')).encode())}.{b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    message = STATE / "jwt-unsigned.txt"
    signature = STATE / "jwt-signature.bin"
    message.write_text(unsigned)
    subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(STATE / "jwt-private.pem"), "-out", str(signature), str(message)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    destination.write_text(f"{unsigned}.{b64url(signature.read_bytes())}")
    destination.chmod(0o600)


def summarize_response(path: Path, label: str) -> None:
    response = json.loads(path.read_text())
    print(f"{label} response:")
    if "reports" in response:
        print(f"  result: {response.get('result')}")
        for report in response["reports"]:
            findings = sum(len(run.get("results", [])) for run in report.get("sarifReport", {}).get("runs", []))
            print(f"  {report.get('specId')}: {report.get('result')}, {findings} finding(s), maturity={report.get('maturity')}")
    elif "insights" in response:
        print(f"  status: {response.get('status')}")
        print(f"  Insights: {response['insights'].get('state')}, published={response['insights'].get('publishedReportCount')}, queued={len(response['insights'].get('unpublishedReports', []))}")
        for config in response.get("configs", []):
            print(f"  config: {config.get('branch')} @ {config.get('commitSha')}, stale={config.get('stale')}")
    else:
        print("  " + json.dumps(response, separators=(",", ":")))
    print(f"  full response saved: {path.relative_to(ROOT)}")


def prepare_lint_request(invalid_config_token: bool = False, request_name: str = "lint-batch") -> None:
    if invalid_config_token:
        token = "deliberately-invalid-config-token"
    else:
        try:
            token = subprocess.run(
                ["gh", "auth", "token", "--hostname", "github.com"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise SystemExit("Sign in with gh auth login --hostname github.com before running the batch lint scenario.") from None
    if not token:
        raise SystemExit("GitHub CLI returned an empty token. Run gh auth login --hostname github.com.")

    request = json.loads((ROOT / "requests" / f"{request_name}.json").read_text())
    request["config"]["git"]["url"] = (
        "https://x-access-token:" + quote(token, safe="")
        + "@github.com/specmatic/private-central-linter-config.git"
    )
    suffix = "invalid-config-token" if invalid_config_token else "authenticated"
    destination = STATE / f"{request_name}-{suffix}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(request, indent=2) + "\n")
    destination.chmod(0o600)


def main() -> None:
    action = sys.argv[1]
    if action == "token":
        create_token("lint:run reports:read" if sys.argv[2] == "good" else "lint:run", STATE / f"{sys.argv[2]}.jwt")
        return
    if action == "summary":
        summarize_response(Path(sys.argv[2]), sys.argv[3])
        return
    if action == "prepare-request":
        prepare_lint_request(request_name=sys.argv[2] if len(sys.argv) > 2 else "lint-batch")
        return
    if action == "prepare-invalid-config-token-request":
        prepare_lint_request(invalid_config_token=True)
        return
    if action == "prepare-clean-request":
        prepare_lint_request(request_name="lint-clean-batch")
        return
    raise SystemExit(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
