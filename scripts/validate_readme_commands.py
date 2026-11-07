#!/usr/bin/env python3
"""Run README command/output pairs in an isolated demo, matching typed templates."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r'<([^<>:]+): ([^<>]+)>')
KINDS = {'UUID', 'ISO 8601 date-time, UTC', '40 hexadecimal characters',
         'positive integer', 'non-negative integer, bytes', 'yyyyMMdd-HHmmss',
         'absolute path', 'string', 'JSON object from the scenario fixture',
         'RS256 JWT, base64url.base64url.base64url'}


@dataclass
class CommandSpec:
    command: str
    expected: str


def parse_readme(path: Path) -> list[CommandSpec]:
    blocks = []
    language = None
    content = []
    indentation = 0
    for line in path.read_text().splitlines():
        if language is None:
            if line.lstrip().startswith('```'):
                language = line.strip()[3:]
                indentation = len(line) - len(line.lstrip())
                content = []
        elif line.strip() == '```':
            blocks.append((language, '\n'.join(content)))
            language = None
        else:
            content.append(line[indentation:] if line[:indentation].isspace() else line)
    if language is not None:
        raise ValueError('Unterminated README code fence')
    specs = []
    for index, (language, command) in enumerate(blocks):
        if language != 'shell':
            continue
        if index + 1 == len(blocks) or blocks[index + 1][0] != 'terminaloutput':
            raise ValueError(f'Missing terminaloutput after command #{len(specs) + 1}')
        expected = blocks[index + 1][1]
        for _, kind in PLACEHOLDER.findall(expected):
            if kind not in KINDS:
                raise ValueError(f'Unknown placeholder type: {kind}')
        specs.append(CommandSpec(command.strip(), expected.strip()))
    if not specs:
        raise ValueError('No shell commands found')
    return specs


def valid_value(kind: str, value) -> bool:
    try:
        if kind == 'UUID':
            return isinstance(value, str) and str(uuid.UUID(value)) == value.lower()
        if kind == 'ISO 8601 date-time, UTC':
            return (isinstance(value, str) and
                    bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value)) and
                    bool(datetime.fromisoformat(value[:-1] + '+00:00')))
        if kind == 'yyyyMMdd-HHmmss':
            return bool(re.fullmatch(r'\d{8}-\d{6}', str(value))) and bool(datetime.strptime(value, '%Y%m%d-%H%M%S'))
        if kind == '40 hexadecimal characters':
            return bool(re.fullmatch(r'[0-9a-fA-F]{40}', str(value)))
        if kind in ('positive integer', 'non-negative integer, bytes'):
            return bool(re.fullmatch(r'\d+', str(value))) and int(value) >= (1 if kind == 'positive integer' else 0)
        if kind == 'absolute path':
            return isinstance(value, str) and Path(value).is_absolute()
        if kind == 'string':
            return isinstance(value, str)
        if kind == 'JSON object from the scenario fixture':
            return isinstance(value, dict)
        if kind == 'RS256 JWT, base64url.base64url.base64url':
            if not isinstance(value, str) or not re.fullmatch(r'[\w-]+\.[\w-]+\.[\w-]+', value, re.ASCII):
                return False
            header, claims, _ = value.split('.')
            decode = lambda part: json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
            return decode(header).get('alg') == 'RS256' and isinstance(decode(claims), dict)
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return False
    raise ValueError(f'Unknown placeholder type: {kind}')


def bind(name, kind, value, bindings):
    if not valid_value(kind, value):
        return False
    if name in bindings and bindings[name] != value:
        return False
    bindings[name] = value
    return True


def value_pattern(kind):
    if kind == 'UUID':
        return r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
    if kind == 'yyyyMMdd-HHmmss':
        return r'\d{8}-\d{6}'
    if kind in ('positive integer', 'non-negative integer, bytes'):
        return r'\d+'
    if kind == '40 hexadecimal characters':
        return r'[0-9a-fA-F]{40}'
    return r'.+?'


def matches(expected, actual, bindings):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and matches(value, actual[key], bindings)
                                                 for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            matches(left, right, bindings) for left, right in zip(expected, actual))
    if not isinstance(expected, str):
        return type(expected) is type(actual) and expected == actual
    placeholder = PLACEHOLDER.fullmatch(expected)
    if placeholder:
        name, kind = placeholder.groups()
        if kind in ('positive integer', 'non-negative integer, bytes') and type(actual) is not int:
            # Text output is handled by the textual branch below.
            return False
        return bind(name, kind, actual, bindings)
    if not isinstance(actual, str):
        return False
    pattern = ''
    end = 0
    placeholders = list(PLACEHOLDER.finditer(expected))
    for token in placeholders:
        pattern += re.escape(expected[end:token.start()]) + '(' + value_pattern(token[2]) + ')' 
        end = token.end()
    pattern += re.escape(expected[end:])
    found = re.fullmatch(pattern, actual)
    return found is not None and all(bind(*token.groups(), value, bindings)
                                     for token, value in zip(placeholders, found.groups()))


def nodes(output: str, template: bool):
    if template:
        # Numeric template values are unquoted in the README.
        output = re.sub(r'(:\s*)(<[^<>]+>)(\s*[,}])', r'\1"\2"\3', output)
    decoder = json.JSONDecoder()
    result = []
    offset = 0
    while offset < len(output):
        while offset < len(output) and output[offset].isspace():
            offset += 1
        if offset == len(output):
            break
        if output[offset] in '{[':
            try:
                value, consumed = decoder.raw_decode(output[offset:])
                result.append(value)
                offset += consumed
                continue
            except ValueError:
                pass
        end = output.find('\n', offset)
        if end < 0:
            end = len(output)
        result.append(output[offset:end].strip())
        offset = end + 1
    return result


def match_output(expected: str, actual: str):
    expected_parts = expected.split('=== Request ===')
    actual_parts = actual.split('=== Request ===')
    if len(expected_parts) != len(actual_parts):
        raise ValueError('Request count differs from the output template')
    for expected_part, actual_part in zip(expected_parts, actual_parts):
        bindings = {}
        actual_nodes = iter(nodes(actual_part, False))
        for expected_node in nodes(expected_part, True):
            for actual_node in actual_nodes:
                candidate = dict(bindings)
                # Entire-line numeric placeholders are textual, unlike JSON fields.
                if isinstance(expected_node, str) and isinstance(actual_node, str) and PLACEHOLDER.fullmatch(expected_node):
                    found = bind(*PLACEHOLDER.fullmatch(expected_node).groups(), actual_node, candidate)
                else:
                    found = matches(expected_node, actual_node, candidate)
                if found:
                    bindings = candidate
                    break
            else:
                raise ValueError(f'Expected output not found or invalid: {expected_node}')


def expected_exit(command: str) -> int:
    return 1 if ('/does-not-exist/' in command or "this-is-not-a-valid-license" in command) else 0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Runner:
    def __init__(self, workspace: Path, timeout: float):
        self.workspace = workspace
        self.timeout = timeout
        self.server = None
        self.processes = []
        self.logs = []

    def launch(self, command):
        log = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
        self.logs.append(log)
        proc = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-c', command], cwd=self.workspace,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append(proc)
        return proc, log

    @staticmethod
    def output(log):
        return os.pread(log.fileno(), os.fstat(log.fileno()).st_size, 0).decode('utf-8', errors='replace')

    @staticmethod
    def stop(proc):
        # demo.sh's EXIT trap stops its own container and fixture process.
        if proc.poll() is None:
            for sig, timeout in ((signal.SIGINT, 15), (signal.SIGTERM, 10), (signal.SIGKILL, 5)):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=timeout)
                    break
                except subprocess.TimeoutExpired:
                    continue

    def stop_server(self):
        if self.server:
            self.stop(self.server)
            self.server = None

    def run(self, command):
        proc, log = self.launch(command)
        try:
            proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.stop(proc)
            raise ValueError(f'Command timed out after {self.timeout:g}s') from None
        return proc.returncode, self.output(log)

    def start(self, command, expected, normalize):
        self.stop_server()
        proc, log = self.launch(command)
        self.server = proc
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise ValueError(f'Server exited before readiness (exit {proc.returncode}); check Docker and the licence')
            output = normalize(self.output(log))
            try:
                match_output(expected, output)
                ca_file = self.workspace / '.demo-state/server-ca'
                ca = ['--cacert', ca_file.read_text().strip()] if ca_file.exists() else []
                url = (self.workspace / '.demo-state/server-url').read_text().strip()
                health = subprocess.run(['curl', '-fsS', '--max-time', '2', *ca, url + '/health'], capture_output=True)
                if health.returncode == 0:
                    return
            except (ValueError, FileNotFoundError):
                pass
            time.sleep(0.25)
        raise ValueError('Server did not become healthy or match the startup template before timeout')

    def close(self):
        for proc in reversed(self.processes):
            self.stop(proc)
        for log in self.logs:
            log.close()


def prepare_workspace(destination: Path):
    for name in ('demo.sh', 'demo.py', 'fixture_server.py', 'scenarios', 'requests', 'specs'):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name)
        else:
            shutil.copy2(source, destination / name)
    ports = []
    while len(ports) < 3:
        port = free_port()
        if port not in ports:
            ports.append(port)
    mapping = dict(zip(('8000', '8443', '8765'), map(str, ports)))
    for path in destination.rglob('*'):
        if path.is_file():
            text = path.read_text()
            for original, replacement in mapping.items():
                text = text.replace(original, replacement)
            path.write_text(text)

    def normalize(output):
        for original, replacement in mapping.items():
            output = re.sub(r'(?<=:)'+replacement+r'\b', original, output)
            output = output.replace('--port=' + replacement, '--port=' + original)
            output = output.replace('"port":' + replacement, '"port":' + original)
        return output
    return normalize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Validate README pairing and template types without running commands')
    parser.add_argument('--no-pull', action='store_true', help='Skip docker pull and use the cached image')
    parser.add_argument('--timeout', type=float, default=180, help='Maximum seconds per command/startup (default: 180)')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    specs = parse_readme(ROOT / 'README.md')
    if args.check_only:
        print(f'PASS: {len(specs)} command/output pairs; all placeholder types recognized.')
        return 0
    for tool in ('docker', 'python3', 'git', 'gh', 'curl', 'openssl', 'nc', 'bash'):
        if not shutil.which(tool):
            raise ValueError(f'Required executable not found: {tool}')
    for command, label in ((['docker', 'info'], 'Docker daemon'),
                           (['gh', 'auth', 'status', '--hostname', 'github.com'], 'GitHub authentication')):
        if subprocess.run(command, capture_output=True, timeout=args.timeout).returncode:
            raise ValueError(f'{label} is not ready')
    passed = skipped = 0
    with tempfile.TemporaryDirectory(prefix='skeptic-readme-') as directory:
        workspace = Path(directory)
        normalize = prepare_workspace(workspace)
        runner = Runner(workspace, args.timeout)
        try:
            for index, spec in enumerate(specs, 1):
                label = spec.command.splitlines()[0]
                prefix = f'[{index}/{len(specs)}]'
                if 'validate_readme_commands.py' in spec.command:
                    print(f'{prefix} SKIP: validator invocation (avoids recursion)', flush=True)
                    skipped += 1
                    continue
                if 'while true;' in spec.command:
                    print(f'{prefix} MANUAL: Insights recovery requires a controllable endpoint and test licence', flush=True)
                    skipped += 1
                    continue
                if spec.command == 'gh auth login --hostname github.com':
                    print(f'{prefix} PASS: existing GitHub authentication checked instead of interactive login', flush=True)
                    passed += 1
                    continue
                if args.no_pull and spec.command.startswith('docker pull '):
                    print(f'{prefix} SKIP: docker pull (--no-pull)', flush=True)
                    skipped += 1
                    continue
                print(f'{prefix} RUN: {label}', flush=True)
                if './demo.sh start' in spec.command:
                    runner.stop_server()
                    if expected_exit(spec.command) == 0:
                        runner.start(spec.command, spec.expected, normalize)
                        passed += 1
                        print(f'{prefix} PASS: startup output and health', flush=True)
                        continue
                code, output = runner.run(spec.command)
                if code != expected_exit(spec.command):
                    raise ValueError(f'Expected exit {expected_exit(spec.command)}, got {code}')
                # Status after publishing is eventually consistent; retry this read-only command.
                deadline = time.monotonic() + min(60, args.timeout)
                while True:
                    try:
                        match_output(spec.expected, normalize(output))
                        break
                    except ValueError:
                        if '07-status-after-lint.sh' not in spec.command or time.monotonic() >= deadline:
                            raise
                        time.sleep(1)
                        code, output = runner.run(spec.command)
                        if code != 0:
                            raise ValueError(f'Status command exited {code}')
                passed += 1
                print(f'{prefix} PASS', flush=True)
        finally:
            runner.close()
    print(f'Validation complete: {passed} passed, {skipped} skipped/manual, 0 failed.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Never print captured scenario output: it includes bearer and GitHub tokens.
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('Validation interrupted; owned processes cleaned up.', file=sys.stderr)
        sys.exit(130)
