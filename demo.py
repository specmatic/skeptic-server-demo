#!/usr/bin/env python3
"""Generate short-lived demo JWTs and print compact response summaries."""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".demo-state"
ISSUER = "http://127.0.0.1:8765/demo-issuer"


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def create_token(scope: str, destination: Path) -> None:
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": "cba-demo-key"}
    claims = {
        "iss": ISSUER,
        "aud": "cba-lint-demo",
        "sub": "cba-demo-caller",
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


def main() -> None:
    action = sys.argv[1]
    if action == "token":
        create_token("lint:run reports:read" if sys.argv[2] == "good" else "lint:run", STATE / f"{sys.argv[2]}.jwt")
        return
    if action == "summary":
        summarize_response(Path(sys.argv[2]), sys.argv[3])
        return
    raise SystemExit(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
