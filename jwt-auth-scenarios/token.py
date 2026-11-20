#!/usr/bin/env python3
"""Generate local demo tokens on demand so expiry scenarios stay reproducible."""
import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from fixture_server import STATE, b64url, ensure_key_pair


def create_token(scenario: str) -> str:
    STATE.mkdir(parents=True, exist_ok=True)
    if not (STATE / "jwt-private.pem").exists() or not (STATE / "jwks.json").exists():
        ensure_key_pair()
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": "skeptic-demo-key"}
    claims = {
        "iss": "http://127.0.0.1:8765/demo-issuer",
        "aud": "skeptic-lint-demo",
        "sub": "jwt-auth-scenario",
        "scope": "lint:run reports:read",
        "exp": now + 1800,
    }
    key = STATE / "jwt-private.pem"
    if scenario == "bad-signature":
        key = STATE / "jwt-auth-untrusted-private.pem"
        if not key.exists():
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            key.chmod(0o600)
    elif scenario == "wrong-audience":
        claims["aud"] = "another-api"
    elif scenario == "expired":
        claims["exp"] = now - 120  # Beyond the server's 30-second leeway.
    elif scenario == "unknown-key":
        header["kid"] = "unpublished-key"
    elif scenario == "unknown-issuer":
        claims["iss"] = "https://untrusted.example/issuer"
    elif scenario == "wrong-scope":
        claims["scope"] = "lint:run"
    elif scenario == "missing-scope":
        del claims["scope"]
    elif scenario == "missing-expiry":
        del claims["exp"]
    elif scenario == "missing-issuer":
        del claims["iss"]
    elif scenario == "missing-audience":
        del claims["aud"]
    elif scenario == "missing-key-id":
        del header["kid"]
    elif scenario == "not-yet-valid":
        claims["nbf"] = now + 300
    elif scenario in ("unsigned", "hs256", "rsa384"):
        header["alg"] = {"unsigned": "none", "hs256": "HS256", "rsa384": "RS384"}[scenario]
    elif scenario == "malformed":
        return "not-a-jwt"
    elif scenario != "valid":
        raise ValueError(f"Unknown JWT scenario: {scenario}")

    unsigned = ".".join(b64url(json.dumps(part, separators=(",", ":")).encode()) for part in (header, claims))
    if scenario == "unsigned":
        signature = b""
    elif scenario == "hs256":
        signature = hmac.new(b"untrusted-demo-secret", unsigned.encode(), hashlib.sha256).digest()
    else:
        signature = subprocess.run(
            ["openssl", "dgst", "-sha384" if scenario == "rsa384" else "-sha256", "-sign", str(key)],
            input=unsigned.encode(), capture_output=True, check=True,
        ).stdout
    return f"{unsigned}.{b64url(signature)}"


if __name__ == "__main__":
    print(create_token(sys.argv[1]))
