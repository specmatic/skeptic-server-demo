#!/usr/bin/env python3
"""Generate short-lived demo JWTs and print compact response summaries."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import urllib.error
from urllib.parse import quote
import urllib.request

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".demo-state"
ISSUER = "http://127.0.0.1:8765/demo-issuer"
LEGACY_AUTHENTICATED_REQUESTS = {
    "lint-batch-authenticated.json", "lint-clean-batch-authenticated.json",
    "lint-mixed-batch-authenticated.json", "lint-missing-spec-authenticated.json",
    "lint-unknown-profile-authenticated.json", "lint-large-spec-authenticated.json",
    "lint-25mb-spec-authenticated.json", "lint-over-25mb-spec-authenticated.json",
    "lint-batch-invalid-config-token.json",
}


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


def build_lint_request(request_name: str, token: str | None) -> dict:
    request = json.loads((ROOT / "requests" / f"{request_name}.json").read_text())
    git = request["config"]["git"]
    git["url"] = os.environ.get("DEMO_CONFIG_REPO_URL", git["url"])
    if os.environ.get("DEMO_CONFIG_BRANCH"):
        git["branch"] = os.environ["DEMO_CONFIG_BRANCH"]
    if token is not None:
        git["token"] = token
    return request


def config_token(invalid: bool = False) -> str | None:
    if invalid:
        return "deliberately-invalid-config-token"
    if os.environ.get("DEMO_CONFIG_TOKEN"):
        return os.environ["DEMO_CONFIG_TOKEN"]
    if os.environ.get("DEMO_NO_CONFIG_TOKEN") == "1":
        return None
    try:
        token = subprocess.run(
            ["gh", "auth", "token", "--hostname", "github.com"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise SystemExit("Sign in with gh auth login --hostname github.com, or set DEMO_CONFIG_TOKEN for a local fixture.") from None
    if not token:
        raise SystemExit("GitHub CLI returned an empty token. Run gh auth login --hostname github.com.")
    return token


def send_lint_request(request_name: str, request_id: str, invalid_token: bool = False) -> tuple[int, bytes, str | None]:
    token = config_token(invalid_token)
    request = build_lint_request(request_name, token)
    payload = json.dumps(request).encode()
    url = (STATE / "server-url").read_text().strip() + "/skeptic/lint/reports"
    headers = {
        "Authorization": f"Bearer {(STATE / 'good.jwt').read_text().strip()}",
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
    }
    ca_file = (STATE / "server-ca").read_text().strip() if (STATE / "server-ca").exists() else None
    context = None
    if url.startswith("https:"):
        import ssl
        context = ssl.create_default_context(cafile=ca_file)
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=context, timeout=300) as response:
            return response.status, response.read(), token
    except urllib.error.HTTPError as error:
        return error.code, error.read(), token


def redact_config_token(body: bytes, token: str | None) -> bytes:
    if not token:
        return body
    encoded = {
        token.encode(), quote(token, safe="").encode(),
        base64.b64encode(f"x-access-token:{token}".encode()),
    }
    for value in sorted(encoded, key=len, reverse=True):
        body = body.replace(value, b"[redacted]")
    return body


def assert_refreshed_report(path: Path, expected_sha: str) -> None:
    response = json.loads(path.read_text())
    actual_sha = response.get("config", {}).get("commitSha")
    if actual_sha != expected_sha:
        raise SystemExit(f"Expected config SHA {expected_sha}, got {actual_sha!r}.")
    marker_found = any(
        result.get("ruleId") == "operation-summary"
        and "CLIENT_VALIDATION_C1" in result.get("message", {}).get("text", "")
        for report in response.get("reports", [])
        for run in report.get("sarifReport", {}).get("runs", [])
        for result in run.get("results", [])
    )
    if not marker_found:
        raise SystemExit("Refreshed report is missing operation-summary / CLIENT_VALIDATION_C1.")
    print(f"PASS: config SHA {expected_sha}; CLIENT_VALIDATION_C1 found in SARIF.")


def post_scenario(request_name: str, label: str, invalid_token: bool = False, response_name: str | None = None,
                  expected_status: int | None = None) -> None:
    request_id = os.environ.get("DEMO_REQUEST_ID") or str(__import__("uuid").uuid4())
    status, body, token = send_lint_request(request_name, request_id, invalid_token)
    body = redact_config_token(body, token)
    response_path = STATE / f"{response_name or request_name + '-response'}.json"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_bytes(body)
    print(f"\n=== Request ===\nPOST {(STATE / 'server-url').read_text().strip()}/skeptic/lint/reports")
    print(f"Authorization: Bearer [redacted]\nContent-Type: application/json\nX-Request-Id: {request_id}")
    print("[request body omitted: may contain credentials]")
    print(f"\n=== Response ===\nHTTP {status}")
    try:
        response_label = response_path.relative_to(ROOT)
    except ValueError:
        response_label = response_path
    if expected_status is not None and status != expected_status:
        raise SystemExit(f"Expected HTTP {expected_status}, got {status}.")
    if invalid_token and status != 422:
        raise SystemExit(f"Expected HTTP 422 for invalid config.git.token, got {status}.")
    if status == 200:
        summarize_response(response_path, label)
    else:
        print(f"\nFull response saved: {response_label}")
        try:
            print(json.dumps(json.loads(body), separators=(",", ":")))
        except (ValueError, UnicodeDecodeError):
            print("[non-JSON response omitted]")


def main() -> None:
    action = sys.argv[1]
    if action == "token":
        create_token("lint:run reports:read" if sys.argv[2] == "good" else "lint:run", STATE / f"{sys.argv[2]}.jwt")
        return
    if action == "summary":
        summarize_response(Path(sys.argv[2]), sys.argv[3])
        return
    if action == "assert-error":
        response = json.loads(Path(sys.argv[2]).read_text())
        expected_code = sys.argv[3]
        actual_code = response.get("code")
        if actual_code != expected_code:
            raise SystemExit(f"Expected error code {expected_code}, got {actual_code!r}")
        print(f"Verified error code: {actual_code}")
        return
    if action == "assert-refresh":
        assert_refreshed_report(Path(sys.argv[2]), sys.argv[3])
        return
    if action == "prepare-request":
        request_name = sys.argv[2] if len(sys.argv) > 2 else "lint-batch"
        label = {
            "lint-batch": "Batch lint", "lint-clean-batch": "Clean batch lint",
            "lint-mixed-batch": "Mixed batch lint", "lint-large-spec": "At-limit YAML lint",
            "lint-25mb-spec": "25 MiB YAML lint", "lint-over-25mb-spec": "Over-limit YAML lint",
            "lint-config-refresh": "Config refresh validation",
        }.get(request_name, "Batch lint")
        post_scenario(request_name, label,
                      response_name=(sys.argv[3] if len(sys.argv) > 3 else None),
                      expected_status=(int(sys.argv[4]) if len(sys.argv) > 4 else None))
        return
    if action == "prepare-invalid-config-token-request":
        post_scenario("lint-batch", "Invalid config token", invalid_token=True,
                      response_name="lint-batch-invalid-config-token")
        return
    if action == "prepare-clean-request":
        post_scenario("lint-clean-batch", "Clean batch lint", response_name="lint-clean-response")
        return
    if action == "cleanup-legacy-requests":
        for name in LEGACY_AUTHENTICATED_REQUESTS:
            path = STATE / name
            if path.exists():
                path.unlink()
        return
    raise SystemExit(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
