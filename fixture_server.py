#!/usr/bin/env python3
"""Local JWKS, spec fixtures, and smart-HTTP Git repository for the demo."""

import base64
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".demo-state"
GIT_ROOT = STATE / "git-root"
PORT = int(os.environ.get("DEMO_FIXTURE_PORT", "8765"))


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def ensure_key_pair() -> None:
    private_key = STATE / "jwt-private.pem"
    public_key = STATE / "jwt-public.der"
    if not private_key.exists():
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        private_key.chmod(0o600)
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER", "-out", str(public_key)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    der = public_key.read_bytes()
    modulus, exponent = rsa_public_numbers(der)
    (STATE / "jwks.json").write_text(
        json.dumps({"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "cba-demo-key", "n": b64url(modulus), "e": b64url(exponent)}]})
    )


def rsa_public_numbers(der: bytes) -> tuple[bytes, bytes]:
    """Read modulus and exponent from SubjectPublicKeyInfo DER."""
    def read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
        tag = data[offset]
        first = data[offset + 1]
        if first < 0x80:
            length, start = first, offset + 2
        else:
            count = first & 0x7F
            length, start = int.from_bytes(data[offset + 2:offset + 2 + count], "big"), offset + 2 + count
        return tag, data[start:start + length], start + length

    _, outer, _ = read_tlv(der, 0)
    _, _, offset = read_tlv(outer, 0)  # algorithm identifier
    _, bit_string, _ = read_tlv(outer, offset)
    _, rsa_sequence, _ = read_tlv(bit_string, 1)  # skip unused-bits byte
    _, modulus, offset = read_tlv(rsa_sequence, 0)
    _, exponent, _ = read_tlv(rsa_sequence, offset)
    return modulus.lstrip(b"\0"), exponent.lstrip(b"\0")


def prepare_git_repo() -> None:
    repo = GIT_ROOT / "config.git"
    if repo.exists():
        return
    STATE.mkdir(parents=True, exist_ok=True)
    work = STATE / "config-work"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    (work / "specmatic-linter.yaml").write_bytes((ROOT / "fixtures/specmatic-linter.yaml").read_bytes())
    subprocess.run(["git", "-C", str(work), "add", "specmatic-linter.yaml"], check=True)
    subprocess.run(["git", "-C", str(work), "-c", "user.name=CBA Demo", "-c", "user.email=demo@example.test", "commit", "-m", "Demo lint configuration"], check=True, capture_output=True)
    GIT_ROOT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--bare", str(work), str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "--git-dir", str(repo), "update-server-info"], check=True, capture_output=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "CbaDemoFixtures/1.0"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/config.git/"):
            self.git_backend()
        elif path == "/jwks.json":
            self.send_file(STATE / "jwks.json", "application/json")
        elif path in ("/specs/orders-api.yaml", "/specs/payments-api.yaml"):
            name = path.rsplit("/", 1)[-1]
            self.send_file(ROOT / "fixtures" / name, "application/yaml")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path.startswith("/config.git/"):
            self.git_backend()
        else:
            self.send_error(404)

    def send_file(self, path: Path, content_type: str) -> None:
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def git_backend(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))) if self.command == "POST" else b""
        env = os.environ.copy()
        env.update({
            "GIT_PROJECT_ROOT": str(GIT_ROOT),
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": urlsplit(self.path).path,
            "QUERY_STRING": urlsplit(self.path).query,
            "REQUEST_METHOD": self.command,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": "",
            "REMOTE_ADDR": self.client_address[0],
            "SERVER_PROTOCOL": "HTTP/1.1",
        })
        result = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True)
        if result.returncode:
            self.send_error(500, "Git fixture backend failed")
            return
        headers, _, payload = result.stdout.partition(b"\r\n\r\n")
        if not payload:
            headers, _, payload = result.stdout.partition(b"\n\n")
        status = 200
        parsed_headers = []
        for line in headers.decode("latin1").splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            if key.lower() == "status":
                status = int(value.strip().split()[0])
            elif key.lower() not in ("connection", "transfer-encoding"):
                parsed_headers.append((key.strip(), value.strip()))
        self.send_response(status)
        for key, value in parsed_headers:
            if key.lower() != "content-length":
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print("fixture:", fmt % args, file=sys.stderr)


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ensure_key_pair()
    prepare_git_repo()
    if len(sys.argv) > 1 and sys.argv[1] == "prepare":
        return
    print(f"Local demo fixtures listening on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
