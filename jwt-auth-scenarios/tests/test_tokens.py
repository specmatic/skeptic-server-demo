"""Check fixture signatures and deliberate claim changes without running a server."""
import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1] / "token.py"
spec = importlib.util.spec_from_file_location("jwt_scenario_tokens", SOURCE)
tokens = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tokens)


def decode(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        for module in (tokens, sys.modules["fixture_server"]):
            patcher = patch.object(module, "STATE", self.state)
            patcher.start()
            self.addCleanup(patcher.stop)
        tokens.create_token("valid")
        subprocess.run([
            "openssl", "pkey", "-in", str(self.state / "jwt-private.pem"),
            "-pubout", "-out", str(self.state / "public.pem"),
        ], check=True, capture_output=True)

    def test_signatures_distinguish_trusted_wrong_key_unsigned_and_hmac_tokens(self):
        for scenario, digest, expected_valid in (
            ("valid", "-sha256", True),
            ("bad-signature", "-sha256", False),
            ("rsa384", "-sha384", True),
        ):
            with self.subTest(scenario=scenario):
                header, payload, signature = tokens.create_token(scenario).split(".")
                signature_file = self.state / "signature.bin"
                signature_file.write_bytes(decode(signature))
                result = subprocess.run([
                    "openssl", "dgst", digest, "-verify", str(self.state / "public.pem"),
                    "-signature", str(signature_file),
                ], input=f"{header}.{payload}".encode(), capture_output=True)
                self.assertEqual(result.returncode == 0, expected_valid)
        unsigned = tokens.create_token("unsigned").split(".")
        self.assertEqual(json.loads(decode(unsigned[0]))["alg"], "none")
        self.assertEqual(unsigned[2], "")
        hs256 = tokens.create_token("hs256").split(".")
        self.assertEqual(json.loads(decode(hs256[0]))["alg"], "HS256")
        self.assertEqual(len(decode(hs256[2])), 32)

    def test_claim_scenarios_change_the_intended_claim_or_header(self):
        for scenario, section, field, expected in (
            ("wrong-audience", 1, "aud", "another-api"),
            ("unknown-issuer", 1, "iss", "https://untrusted.example/issuer"),
            ("unknown-key", 0, "kid", "unpublished-key"),
            ("wrong-scope", 1, "scope", "lint:run"),
        ):
            with self.subTest(scenario=scenario):
                part = tokens.create_token(scenario).split(".")[section]
                self.assertEqual(json.loads(decode(part))[field], expected)
        for scenario, section, field in (
            ("missing-audience", 1, "aud"), ("missing-issuer", 1, "iss"),
            ("missing-expiry", 1, "exp"), ("missing-scope", 1, "scope"),
            ("missing-key-id", 0, "kid"),
        ):
            with self.subTest(scenario=scenario):
                self.assertNotIn(field, json.loads(decode(tokens.create_token(scenario).split(".")[section])))
        now = time.time()
        expired = json.loads(decode(tokens.create_token("expired").split(".")[1]))
        future = json.loads(decode(tokens.create_token("not-yet-valid").split(".")[1]))
        self.assertLess(expired["exp"], now - 30)
        self.assertGreater(future["nbf"], now + 30)
        self.assertEqual(tokens.create_token("malformed"), "not-a-jwt")


if __name__ == "__main__":
    unittest.main()
