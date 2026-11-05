#!/usr/bin/env python3
"""Local JWKS and API-spec fixtures for the demo."""

import base64
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".demo-state"
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


class Handler(BaseHTTPRequestHandler):
    server_version = "CbaDemoFixtures/1.0"

    def do_GET(self) -> None:
        if self.path == "/jwks.json":
            self.send_file(STATE / "jwks.json", "application/json")
        elif self.path in (
            "/specs/orders-api.yaml", "/specs/payments-api.yaml",
            "/specs/orders-api-clean.yaml", "/specs/payments-api-clean.yaml",
        ):
            name = self.path.rsplit("/", 1)[-1]
            self.send_file(ROOT / "fixtures" / name, "application/yaml")
        else:
            self.send_error(404)

    def send_file(self, path: Path, content_type: str) -> None:
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print("fixture:", fmt % args, file=sys.stderr)


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ensure_key_pair()
    if len(sys.argv) > 1 and sys.argv[1] == "prepare":
        return
    print(f"Local demo fixtures listening on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
