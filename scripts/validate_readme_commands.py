#!/usr/bin/env python3
"""Run the runnable shell examples from README.md in an isolated demo copy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def read_commands(readme: Path) -> list[str]:
    commands = []
    in_shell = False
    current = []
    for line in readme.read_text().splitlines():
        if not in_shell:
            if line.strip() == "```shell":
                in_shell = True
                current = []
        elif line.strip() == "```":
            command = "\n".join(current).strip()
            if command:
                commands.append(command)
            in_shell = False
        else:
            current.append(line)
    if in_shell:
        raise ValueError("README has an unterminated shell block")
    if not commands:
        raise ValueError("README contains no shell commands")
    return commands


def free_ports(count: int) -> list[int]:
    ports = []
    while len(ports) < count:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in ports:
            ports.append(port)
    return ports


def prepare_workspace(destination: Path, ports: list[int]) -> None:
    for name in ("demo.sh", "demo.py", "fixture_server.py", "scenarios", "jwt-auth-scenarios", "requests", "specs"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name)
        else:
            shutil.copy2(source, destination / name)
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for source_port, target_port in zip((8000, 8443, 8765), ports):
            text = text.replace(str(source_port), str(target_port))
        text = text.replace(
            'CONFIG_REPO_URL="${SPECMATIC_CONFIG_REPO_URL:?Set SPECMATIC_CONFIG_REPO_URL to your config repository HTTPS URL}"',
            'CONFIG_REPO_URL="${SPECMATIC_CONFIG_REPO_URL:?Set SPECMATIC_CONFIG_REPO_URL}"')
        text = text.replace(
            'https://github.com/YOUR-ORG/YOUR-LINTER-CONFIG.git',
            'https://github.com/validator/linter-config.git')
        path.write_text(text)


class Validator:
    def __init__(self, workspace: Path, timeout: float):
        self.workspace = workspace
        self.timeout = timeout
        self.server: subprocess.Popen | None = None

    def stop_server(self) -> None:
        if self.server and self.server.poll() is None:
            try:
                os.killpg(self.server.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            except PermissionError:
                try:
                    self.server.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
            try:
                self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.server.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    self.server.kill()
                self.server.wait()
        self.server = None

    def run(self, command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", command], cwd=self.workspace,
            env=env, capture_output=True, text=True, timeout=self.timeout)

    def start(self, command: str, env: dict[str, str]) -> None:
        self.stop_server()
        self.server = subprocess.Popen(
            ["bash", "-e", "-o", "pipefail", "-c", command], cwd=self.workspace,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        state = self.workspace / ".demo-state"
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise ValueError("Lint server exited during startup; check Docker and the service-account license")
            try:
                url = (state / "server-url").read_text().strip()
                port = (state / "server-port").read_text().strip()
                ca_file = state / "server-ca"
                ca = ["--cacert", ca_file.read_text().strip()] if ca_file.exists() else []
                health = subprocess.run(["curl", "-fsS", "--max-time", "2", *ca, url + "/health"],
                                        capture_output=True, text=True)
                if health.returncode == 0 and json.loads(health.stdout).get("status") == "up":
                    return
                if port:
                    ready = subprocess.run(["curl", "-sS", "--max-time", "2", *ca, url + "/readiness"],
                                           capture_output=True, text=True)
                    if ready.returncode == 0 and json.loads(ready.stdout).get("status") == "ready":
                        return
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            time.sleep(0.25)
        raise ValueError("Lint server did not become healthy before timeout")

    def close(self) -> None:
        self.stop_server()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Check that README contains shell examples")
    parser.add_argument("--no-pull", action="store_true", help="Use the cached Docker image")
    parser.add_argument("--timeout", type=float, default=60, help="Timeout per command/startup in seconds")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    commands = read_commands(ROOT / "README.md")
    if args.check_only:
        print(f"PASS: found {len(commands)} README shell examples")
        return 0

    for tool in ("docker", "python3", "gh", "curl", "openssl", "nc", "bash"):
        if not shutil.which(tool):
            raise ValueError(f"Required executable not found: {tool}")
    if subprocess.run(["docker", "info"], capture_output=True, timeout=args.timeout).returncode:
        raise ValueError("Docker daemon is not ready")
    if subprocess.run(["gh", "auth", "status", "--hostname", "github.com"],
                      capture_output=True, timeout=args.timeout).returncode:
        raise ValueError("GitHub CLI is not authenticated")

    passed = skipped = 0
    with tempfile.TemporaryDirectory(prefix="skeptic-readme-") as temporary:
        workspace = Path(temporary)
        ports = free_ports(3)
        prepare_workspace(workspace, ports)
        validator = Validator(workspace, args.timeout)
        env = os.environ.copy()
        env["SPECMATIC_CONFIG_REPO_URL"] = "https://github.com/validator/linter-config.git"
        try:
            for index, command in enumerate(commands, 1):
                label = command.splitlines()[0]
                prefix = f"[{index}/{len(commands)}]"
                if "validate_readme_commands.py" in command or "gh auth login" in command:
                    skipped += 1
                    print(f"{prefix} SKIP: manual or recursive command", flush=True)
                    continue
                if "while true;" in command:
                    skipped += 1
                    print(f"{prefix} SKIP: requires a controllable Insights endpoint", flush=True)
                    continue
                if "SPECMATIC_LICENSE_PATH=" in command or "SPECMATIC_LICENSE_CONTENT=" in command:
                    skipped += 1
                    print(f"{prefix} SKIP: optional license troubleshooting", flush=True)
                    continue
                if command == "./demo.sh start --https":
                    skipped += 1
                    print(f"{prefix} SKIP: optional HTTPS startup", flush=True)
                    continue
                if args.no_pull and command.startswith("docker pull "):
                    skipped += 1
                    print(f"{prefix} SKIP: docker pull (--no-pull)", flush=True)
                    continue
                print(f"{prefix} RUN: {label}", flush=True)
                if "./demo.sh start" in command:
                    print(
                        f"{prefix} Specmatic image: "
                        f"{env.get('SPECMATIC_ENTERPRISE_IMAGE', 'specmatic/enterprise:latest')}",
                        flush=True,
                    )
                    validator.start(command, env)
                    passed += 1
                    print(f"{prefix} PASS: server healthy", flush=True)
                    continue
                result = validator.run(command, env)
                if result.returncode != 0:
                    if "01-health.sh" in command:
                        raise ValueError(f"Health scenario failed: {result.stderr.strip() or 'no error output'}")
                    raise ValueError(f"{label} failed (exit {result.returncode})")
                if "jwt-auth-scenarios/run_all.py" in command:
                    print(result.stdout, end="", flush=True)
                if "05-status-before-lint.sh" in command or "07-status-after-lint.sh" in command:
                    status_path = workspace / ".demo-state/status-before.json"
                    if "07-status-after-lint.sh" in command:
                        status_path = workspace / ".demo-state/status-after.json"
                    status = json.loads(status_path.read_text())
                    if status.get("status") not in ("ready", "not_ready") or not isinstance(status.get("configs"), list):
                        raise ValueError(f"{label} returned an invalid status document")
                passed += 1
                print(f"{prefix} PASS", flush=True)
        finally:
            validator.close()
    print(f"Validation complete: {passed} passed, {skipped} skipped/manual, 0 failed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        if isinstance(error, OSError):
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Validation interrupted; owned processes cleaned up.", file=sys.stderr)
        sys.exit(130)
