#!/usr/bin/env python3
"""Run every manual JWT scenario against the existing server and assert responses."""
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from email.parser import Parser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MESSAGES = {
    "INVALID_TOKEN": "The Bearer token is invalid or expired.",
    "AUTHENTICATION_REQUIRED": "A Bearer token is required.",
    "ACCESS_DENIED": "JWT does not satisfy the configured claim values.",
    "INVALID_REQUEST": "X-Request-Id must be a valid UUID.",
    "UNSUPPORTED_MEDIA_TYPE": "The request Content-Type must be application/json.",
}


def expectation(script):
    lines = [line for line in script.read_text().splitlines() if line.startswith("run_jwt_case ")]
    if len(lines) != 1:
        raise ValueError(f"{script.name}: expected one run_jwt_case declaration")
    _, scenario, status, code, *mode = shlex.split(lines[0])
    if code not in MESSAGES or len(mode) > 1:
        raise ValueError(f"{script.name}: unsupported scenario declaration")
    return scenario, int(status), code, mode[0] if mode else "supplied"


def check_response(directory, expected):
    scenario, expected_status, code, mode = expected
    raw_headers = (directory / "headers.txt").read_text()
    # Curl can save proxy CONNECT / interim headers before the actual response.
    blocks = re.split(r"(?m)^(?=HTTP/\S+\s+\d{3})", raw_headers)
    final = [block for block in blocks if block.startswith("HTTP/")][-1]
    status_line, _, header_lines = final.partition("\n")
    actual_status = int(status_line.split()[1])
    headers = Parser().parsestr(header_lines)
    raw_body = (directory / "body.json").read_text()
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(actual_status == expected_status, f"Expected HTTP {expected_status}; received {actual_status}")
    require(bool(raw_body.strip()), f"HTTP {actual_status} returned an empty body; required JSON code, message and requestId are missing")
    try:
        body = json.loads(raw_body)
    except ValueError:
        return errors + ["Response body is not valid JSON"], None
    if not isinstance(body, dict):
        return errors + ["Response JSON must be an object"], None

    require(body.get("code") == code, f"Expected code={code!r}; received {body.get('code')!r}")
    require(body.get("message") == MESSAGES[code], f"Expected message={MESSAGES[code]!r}; received {body.get('message')!r}")
    request_id = body.get("requestId")
    valid_id = False
    try:
        valid_id = isinstance(request_id, str) and str(uuid.UUID(request_id)) == request_id.lower()
    except (ValueError, TypeError, AttributeError):
        pass
    require(valid_id, f"requestId must be a UUID string; received {request_id!r}")
    require(headers.get_all("X-Request-Id", []) == [request_id], "Expected exactly one X-Request-Id header matching JSON requestId")
    supplied_id = (directory / "request-id").read_text()
    if mode == "supplied":
        require(bool(supplied_id) and request_id == supplied_id, f"Server must preserve supplied requestId {supplied_id!r}; received {request_id!r}")
    if mode == "malformed":
        require(request_id != "not-a-uuid", "Malformed supplied requestId must be replaced")
        require(body.get("details") == [{"field": "X-Request-Id", "message": "Supply a UUID or omit the header."}], "Malformed requestId must identify X-Request-Id in error details")
    content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    require(content_type == "application/json", f"Expected Content-Type application/json; received {headers.get('Content-Type', '<missing>')!r}")
    require(headers.get("Cache-Control") == "no-store", f"Expected Cache-Control no-store; received {headers.get('Cache-Control', '<missing>')!r}")
    if expected_status == 401:
        require(headers.get_all("WWW-Authenticate", []) == ['Bearer realm="Skeptic Server"'], "Every HTTP 401 must include exactly one Bearer challenge with realm Skeptic Server")
    return errors, request_id if valid_id else None


def main():
    scripts = sorted(HERE.glob("[0-9][0-9]-*.sh"))
    if not scripts:
        raise SystemExit("No numbered JWT scenarios found")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / ".demo-state" / "jwt-auth-results" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    output.mkdir(parents=True)
    cases = [(script.stem, script) for script in scripts]
    # Each script targets the same already-running server; no server lifecycle commands.
    cases += [(f"isolation-{index}-{script.stem}", script) for index, script in enumerate((scripts[0], scripts[1], scripts[0]), 1)]
    failures = 0
    request_ids = set()
    for label, script in cases:
        directory = output / label
        directory.mkdir()
        env = os.environ.copy()
        env.pop("DEMO_REQUEST_ID", None)  # Each automated request gets a fresh UUID.
        env["JWT_AUTH_RESULTS_DIR"] = str(directory)
        try:
            expected = expectation(script)
            result = subprocess.run(["bash", str(script)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=35)
            if result.returncode:
                # stdout includes demo Authorization headers; avoid replaying them.
                raise RuntimeError(f"Scenario command exited {result.returncode}: {result.stderr.strip()}")
            errors, request_id = check_response(directory, expected)
            if request_id:
                if request_id in request_ids:
                    errors.append(f"requestId reused across requests: {request_id}")
                request_ids.add(request_id)
            if errors:
                raise RuntimeError("; ".join(errors))
            print(f"PASS {label}", flush=True)
        except (OSError, ValueError, IndexError, RuntimeError, subprocess.TimeoutExpired) as error:
            failures += 1
            print(f"FAIL {label}: {error}", flush=True)
    print(f"\n{len(cases) - failures} passed; {failures} failed. Responses: {output.relative_to(ROOT)}")
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
