#!/usr/bin/env python3
"""Run controlled HTTP config-refresh checks against the packaged Enterprise image."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid

DEMO_ROOT = Path(__file__).resolve().parents[1]
ENTERPRISE_ROOT = Path(os.environ.get("ENTERPRISE_REPO", DEMO_ROOT.parent / "enterprise")).resolve()
LICENSE = ENTERPRISE_ROOT / "linter/contract-tests/lint-server-test-license.txt"
MOCK_COMPOSE = ENTERPRISE_ROOT / "linter/contract-tests/docker-compose.yaml"
IMAGE = os.environ.get("SPECMATIC_ENTERPRISE_IMAGE", "specmatic/enterprise-snapshots:1.29.3")
TOKEN_A = "local-validation-token-A"
TOKEN_B = "local-validation-token-B"
BAD_TOKEN = "local-validation-token-invalid"
LEGACY_TOKEN = "local-validation-token-legacy"
SPEC = b'''openapi: 3.0.3
info:
  title: Orders
  version: "1"
paths:
  /orders:
    get:
      parameters:
        - name: x-request-id
          in: header
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
'''


def run(*args, env=None, capture=True):
    result = subprocess.run(
        [str(arg) for arg in args], check=True, env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout.decode().strip() if capture else ""


def git(directory: Path, *args: str) -> str:
    return run("git", "-C", directory, *args)


def rules(enabled: bool) -> str:
    severity = "error" if enabled else "off"
    message = "\n          message: CLIENT_VALIDATION_C1" if enabled else ""
    return f'''profiles:
  default:
    rules:
      extends: [recommended]
      override:
        operation-summary:
          severity: {severity}{message}
'''


def has_marker(response: dict) -> bool:
    return any(
        result.get("ruleId") == "operation-summary"
        and "CLIENT_VALIDATION_C1" in result.get("message", {}).get("text", "")
        for report in response.get("reports", [])
        for run in report.get("sarifReport", {}).get("runs", [])
        for result in run.get("results", [])
    )


def json_request(base: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def request(repo_url: str, token=TOKEN_A, download_url="") -> dict:
    git_config = {"url": repo_url, "branch": "main"}
    if token is not None:
        git_config["token"] = token
    return {
        "config": {"git": git_config},
        "repository": {
            "id": "local-refresh-validation", "url": "https://example.invalid/specs.git", "branch": "main",
            "specifications": [{"id": "orders", "path": "orders.yaml", "downloadUrl": download_url}],
        },
    }


class GitFixture:
    def __init__(self, root: Path):
        self.root = root
        self.token = TOKEN_A
        self.failure = None
        self.auth_headers = []
        self.source = root / "source"
        self.bare = root / "rules.git"
        self._init_repository()
        self.server = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://host.docker.internal:{self.server.server_port}/rules.git"
        self.spec_url = f"http://host.docker.internal:{self.server.server_port}/spec.yaml"

    def _init_repository(self):
        self.source.mkdir(parents=True)
        run("git", "-C", self.source, "init", "-b", "main")
        run("git", "init", "--bare", "--initial-branch=main", self.bare)
        git(self.source, "remote", "add", "origin", self.bare)
        self.commit(rules(False))

    def commit(self, content: str) -> str:
        (self.source / "specmatic-linter.yaml").write_text(content)
        git(self.source, "add", ".")
        run("git", "-C", self.source, "-c", "user.name=Validation", "-c", "user.email=validation@example.invalid",
            "commit", "-m", "update rules")
        git(self.source, "push", "--force", "origin", "main")
        return git(self.source, "rev-parse", "HEAD")

    def _handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path == "/spec.yaml":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/yaml")
                    self.send_header("Content-Length", str(len(SPEC)))
                    self.end_headers()
                    self.wfile.write(SPEC)
                    return
                self._serve_git()

            def do_POST(self):
                self._serve_git()

            def _serve_git(self):
                authorization = self.headers.get("Authorization")
                fixture.auth_headers.append(authorization)
                if fixture.failure:
                    self.send_response(fixture.failure)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                expected = "Basic " + base64.b64encode(f"x-access-token:{fixture.token}".encode()).decode()
                if authorization != expected:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="rules"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                query = self.path.partition("?")
                env = dict(
                    os.environ,
                    GIT_PROJECT_ROOT=str(fixture.root), GIT_HTTP_EXPORT_ALL="1",
                    PATH_INFO=query[0], QUERY_STRING=query[2], REQUEST_METHOD=self.command,
                    CONTENT_TYPE=self.headers.get("Content-Type", ""),
                    HTTP_GIT_PROTOCOL=self.headers.get("Git-Protocol", ""), REMOTE_USER="fixture",
                )
                payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                backend = run("git", "--exec-path") + "/git-http-backend"
                result = subprocess.run([backend], input=payload, env=env, capture_output=True, check=True)
                headers, _, body = result.stdout.partition(b"\r\n\r\n")
                self.send_response(200)
                for line in headers.split(b"\r\n"):
                    if b":" not in line:
                        continue
                    key, value = line.decode().split(":", 1)
                    if key.lower() not in ("status", "content-length"):
                        self.send_header(key, value.strip())
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def wait_ready(base: str, timeout: int = 45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = json_request(base, "/health")
            if status == 200:
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Lint server failed startup; inspect its container logs.")


def wait_fresh(base: str, sha: str, timeout: int):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, status = json_request(base, "/status")
        if any(config.get("commitSha") == sha and config.get("stale") is False
               for config in status.get("configs", [])):
            return
        time.sleep(5)
    raise RuntimeError(f"Config SHA {sha} did not become fresh within {timeout} seconds.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Skip the five-minute scheduled-refresh wait")
    args = parser.parse_args()
    if not LICENSE.is_file() or not MOCK_COMPOSE.is_file():
        raise SystemExit(f"Enterprise test license and contract mocks required under {ENTERPRISE_ROOT}.")

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid())
    work = DEMO_ROOT / ".demo-state" / "config-refresh-validation" / run_id
    work.mkdir(parents=True)
    evidence_path = work / "evidence.json"
    evidence = {
        "runId": run_id,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "image": IMAGE,
        "mode": "smoke" if args.smoke else "scheduled-refresh",
        "result": "RUNNING",
        "checks": {},
    }

    def save_evidence():
        evidence["updatedAt"] = datetime.now(timezone.utc).isoformat()
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")

    save_evidence()
    workspace = work / "workspace"
    workspace.mkdir()
    project = "config-refresh-" + uuid.uuid4().hex[:10]
    container = project + "-server"
    compose = ["docker", "compose", "--project-name", project, "-f", MOCK_COMPOSE]
    image = IMAGE
    env = dict(os.environ, ENTERPRISE_IMAGE=image, CENTRAL_CONFIG_REPO_TOKEN=TOKEN_A)
    fixture = GitFixture(work / "git")
    home = work / "credential-home"
    home.mkdir()
    (home / ".netrc").write_text(f"machine host.docker.internal login x-access-token password {TOKEN_A}\n")
    (home / ".netrc").chmod(0o600)
    base = ""

    try:
        subprocess.run(compose + ["up", "-d", "--wait", "mocks"], env=env, check=True)
        run(
            "docker", "run", "-d", "--name", container, "--network", project + "_default",
            "-p", "127.0.0.1::8000", "--workdir", "/workspace",
            "-v", f"{workspace}:/workspace", "-v", f"{home}:/credential-home:ro",
            "-e", "HOME=/credential-home", "-v", f"{LICENSE}:/license.txt:ro",
            "-e", "SPECMATIC_LICENSE_PATH=/license.txt", "-e", "SPECMATIC_DISABLE_TELEMETRY=true",
            "-e", "CENTRAL_CONFIG_REPO_TOKEN", image, "lint-server", "--port", "8000",
            "--allowed-config-repo-url", fixture.url, "--allowed-spec-download-host", "host.docker.internal", "--debug",
            env=env,
        )
        port = json.loads(run("docker", "inspect", container))[0]["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"]
        base = "http://127.0.0.1:" + port
        wait_ready(base)

        # Simulate a prior version's owned cache entry; startup must remove only it.
        legacy_url = fixture.url.replace("http://", f"http://x-access-token:{LEGACY_TOKEN}@")
        legacy = workspace / ".specmatic-linter/repos" / hashlib.sha256((legacy_url + "\0main").encode()).hexdigest()
        legacy.mkdir(parents=True)
        run("git", "-C", legacy, "init", "-b", "main")
        git(legacy, "remote", "add", "origin", legacy_url)
        # Restart to exercise startup migration with this legacy checkout present.
        run("docker", "rm", "-f", container)
        run(
            "docker", "run", "-d", "--name", container, "--network", project + "_default",
            "-p", "127.0.0.1::8000", "--workdir", "/workspace",
            "-v", f"{workspace}:/workspace", "-v", f"{home}:/credential-home:ro",
            "-e", "HOME=/credential-home", "-v", f"{LICENSE}:/license.txt:ro",
            "-e", "SPECMATIC_LICENSE_PATH=/license.txt", "-e", "SPECMATIC_DISABLE_TELEMETRY=true",
            "-e", "CENTRAL_CONFIG_REPO_TOKEN", image, "lint-server", "--port", "8000",
            "--allowed-config-repo-url", fixture.url, "--allowed-spec-download-host", "host.docker.internal", "--debug",
            env=env,
        )
        port = json.loads(run("docker", "inspect", container))[0]["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"]
        base = "http://127.0.0.1:" + port
        wait_ready(base)
        assert not legacy.exists(), "startup did not remove verified credentialed checkout"
        evidence["checks"]["legacy-cache-cleanup"] = "PASS"

        code, body = json_request(base, "/skeptic/lint/reports", request(legacy_url, download_url=fixture.spec_url))
        assert (code, body.get("code")) == (422, "INVALID_CONFIG_URL")
        assert body.get("message") == "config.git.url must not contain credentials. Supply the token separately in config.git.token."
        assert legacy_url not in json.dumps(body)
        evidence["checks"]["credentialed-url"] = {"http": code, "code": body["code"]}
        auth_start = len(fixture.auth_headers)
        code, body = json_request(base, "/skeptic/lint/reports", request(fixture.url, token=None, download_url=fixture.spec_url))
        assert (code, body.get("code")) == (422, "INVALID_CONFIG_TOKEN"), "ambient .netrc/server token unexpectedly authenticated request"
        assert all(header in (None, "") for header in fixture.auth_headers[auth_start:]), "missing token sent implicit auth"
        evidence["checks"]["missing-token-with-netrc"] = {"http": code, "code": body["code"]}
        code, body = json_request(base, "/skeptic/lint/reports", request(fixture.url, BAD_TOKEN, fixture.spec_url))
        assert (code, body.get("code")) == (422, "INVALID_CONFIG_TOKEN")
        evidence["checks"]["wrong-token"] = {"http": code, "code": body["code"]}
        for failure in (403, 404):
            fixture.failure = failure
            code, body = json_request(base, "/skeptic/lint/reports", request(fixture.url, TOKEN_A, fixture.spec_url))
            assert (code, body.get("code")) == (422, "CONFIG_INVALID")
            evidence["checks"][f"http-{failure}"] = {"http": code, "code": body["code"]}
        fixture.failure = None
        print("PASS: credential-free URL rejection, missing/wrong token, .netrc isolation, safe 403/404 classification")

        code, first = json_request(base, "/skeptic/lint/reports", request(fixture.url, TOKEN_A, fixture.spec_url))
        if code != 200:
            evidence["initialLint"] = {"http": code, "code": first.get("code")}
            raise AssertionError("initial lint/config clone failed")
        if not first.get("config", {}).get("commitSha"):
            evidence["initialResponseKeys"] = sorted(first)
            evidence["initialConfigKeys"] = sorted(first.get("config", {})) if isinstance(first.get("config"), dict) else []
            raise AssertionError("initial response omitted config SHA")
        assert not has_marker(first), "C0 unexpectedly contains the CLIENT_VALIDATION_C1 marker"
        expected_sha = first["config"]["commitSha"]
        evidence["initialCommitSha"] = expected_sha
        evidence["checks"]["marker-absent-at-C0"] = "PASS"
        expected_auth = "Basic " + base64.b64encode(f"x-access-token:{TOKEN_A}".encode()).decode()
        assert expected_auth in fixture.auth_headers, "Git did not use expected Authorization header"

        if args.smoke:
            fixture.token = TOKEN_B
            fixture.commit("profiles: [\n")
            code, body = json_request(base, "/skeptic/lint/reports", request(fixture.url, TOKEN_B, fixture.spec_url))
            assert (code, body.get("code")) == (422, "CONFIG_INVALID")
            restored = fixture.commit(rules(True))
            code, body = json_request(base, "/skeptic/lint/reports", request(fixture.url, TOKEN_B, fixture.spec_url))
            if code != 200 or body.get("config", {}).get("commitSha") != restored:
                evidence["recoveryResponse"] = {"http": code, "code": body.get("code"),
                                                 "hasConfigSha": bool(body.get("config", {}).get("commitSha"))}
                raise AssertionError("valid config did not recover after malformed YAML")
            assert has_marker(body), "refreshed custom marker missing from SARIF"
            print("PASS: credential rotation, malformed config recovery")
            evidence["checks"]["credential-rotation-and-config-recovery"] = "PASS"
            evidence["checks"]["marker-rule"] = "PASS"
            evidence["finalCommitSha"] = restored
        else:
            before_logs = run("docker", "logs", container)
            clones_before = before_logs.count("Cloning config repo...")
            expected_sha = fixture.commit(rules(True))
            print("Pushed local C1; polling /status only for scheduled refresh (maximum 360s).", flush=True)
            pushed_at = datetime.now(timezone.utc)
            refresh_started = time.monotonic()
            wait_fresh(base, expected_sha, 360)
            evidence["pushAt"] = pushed_at.isoformat()
            evidence["refreshObservedAt"] = datetime.now(timezone.utc).isoformat()
            evidence["refreshDurationSeconds"] = round(time.monotonic() - refresh_started, 1)
            evidence["refreshedCommitSha"] = expected_sha
            code, second = json_request(base, "/skeptic/lint/reports", request(fixture.url, TOKEN_A, fixture.spec_url))
            assert code == 200 and second["config"]["commitSha"] == expected_sha
            assert first["reports"] != second["reports"], "refreshed config did not change lint result"
            assert has_marker(second), "refreshed custom marker missing from SARIF"
            print("PASS: five-minute background refresh updated SHA and changed lint result")
            evidence["checks"]["scheduled-refresh"] = "PASS"
            evidence["checks"]["marker-rule"] = "PASS"

        logs = run("docker", "logs", container)
        for secret in (TOKEN_A, TOKEN_B, BAD_TOKEN, LEGACY_TOKEN):
            assert secret not in logs, "fixture credential found in server logs"
            for path in work.rglob("*"):
                if path.is_file() and path != home / ".netrc":
                    assert secret.encode() not in path.read_bytes(), "fixture credential found in validation artifacts"
        if not args.smoke:
            assert logs.count("Cloning config repo...") == clones_before, "background refresh cloned instead of fetching"
            evidence["checks"]["refresh-used-fetch"] = "PASS"
        evidence["checks"]["credential-scan-logs-cache"] = "PASS"
        evidence["result"] = "PASS"
        print(f"PASS: no fixture credentials in logs/cache; sanitized evidence: {evidence_path}")
        return 0
    except Exception as error:
        evidence["result"] = "FAIL"
        evidence["errorType"] = type(error).__name__
        evidence["errorLine"] = traceback.extract_tb(error.__traceback__)[-1].lineno
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(compose + ["down", "--volumes", "--remove-orphans"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fixture.close()
        save_evidence()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"FAIL: {type(error).__name__} at line {traceback.extract_tb(error.__traceback__)[-1].lineno}")
        raise SystemExit(1)
