"""Exercise response assertions and suite exit behavior without network services."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "run_all.py"
spec = importlib.util.spec_from_file_location("jwt_scenario_runner", SOURCE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.request_id = str(uuid.uuid4())

    def response(self, directory=None, status=401, code="INVALID_TOKEN", mode="supplied"):
        directory = directory or self.directory
        body = {"code": code, "message": runner.MESSAGES[code], "requestId": self.request_id}
        if mode == "malformed":
            body["details"] = [{"field": "X-Request-Id", "message": "Supply a UUID or omit the header."}]
        headers = (
            f"HTTP/1.1 {status} Response\nContent-Type: application/json; charset=UTF-8\n"
            f"X-Request-Id: {self.request_id}\nCache-Control: no-store\n"
        )
        if status == 401:
            headers += 'WWW-Authenticate: Bearer realm="Skeptic Server"\n'
        (directory / "headers.txt").write_text(headers + "\n")
        (directory / "body.json").write_text(json.dumps(body))
        (directory / "request-id").write_text(self.request_id if mode == "supplied" else "")

    def test_accepts_json_errors_with_matching_request_ids_and_interim_headers(self):
        self.response()
        headers = self.directory / "headers.txt"
        headers.write_text("HTTP/1.1 100 Continue\n\n" + headers.read_text())

        errors, request_id = runner.check_response(self.directory, ("bad-signature", 401, "INVALID_TOKEN", "supplied"))

        self.assertEqual(errors, [])
        self.assertEqual(request_id, self.request_id)

    def test_rejects_bare_401_with_missing_json_error_fields(self):
        self.response()
        (self.directory / "headers.txt").write_text("HTTP/1.1 401 Unauthorized\n\n")
        (self.directory / "body.json").write_text("")

        errors, _ = runner.check_response(self.directory, ("bad-signature", 401, "INVALID_TOKEN", "supplied"))

        self.assertTrue(any("empty body" in error for error in errors), errors)

    def test_detects_wrong_status_code_message_uuid_and_correlation_header(self):
        expected = ("bad-signature", 401, "INVALID_TOKEN", "supplied")
        for field, bad_value in (("code", "OTHER"), ("message", ""), ("requestId", "not-a-uuid"), ("requestId", [])):
            with self.subTest(field=field):
                self.response()
                body_file = self.directory / "body.json"
                body = json.loads(body_file.read_text())
                body[field] = bad_value
                body_file.write_text(json.dumps(body))
                errors, _ = runner.check_response(self.directory, expected)
                self.assertTrue(errors, field)
        self.response(status=200)
        errors, _ = runner.check_response(self.directory, expected)
        self.assertTrue(any("Expected HTTP 401" in error for error in errors), errors)
        self.response()
        headers = self.directory / "headers.txt"
        headers.write_text(headers.read_text().replace(self.request_id, str(uuid.uuid4())))
        errors, _ = runner.check_response(self.directory, expected)
        self.assertTrue(any("X-Request-Id" in error for error in errors), errors)

    def test_rejects_missing_cache_control_and_bearer_challenge(self):
        for old, new in (
            ("Cache-Control: no-store", "Cache-Control: public"),
            ('WWW-Authenticate: Bearer realm="Skeptic Server"\n', ""),
            ("Skeptic Server", "Ktor Server"),
        ):
            with self.subTest(header=old):
                self.response()
                headers = self.directory / "headers.txt"
                headers.write_text(headers.read_text().replace(old, new))
                errors, _ = runner.check_response(self.directory, ("bad-signature", 401, "INVALID_TOKEN", "supplied"))
                self.assertTrue(errors, old)

    def test_suite_continues_after_failed_assertion_and_returns_nonzero(self):
        calls = []

        def execute(command, **kwargs):
            script = Path(command[1])
            _, status, code, mode = runner.expectation(script)
            directory = Path(kwargs["env"]["JWT_AUTH_RESULTS_DIR"])
            self.request_id = str(uuid.uuid4())
            self.response(directory, status, code, mode)
            if not calls:
                (directory / "body.json").write_text("")
            calls.append(script)
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        output = io.StringIO()
        with patch.object(runner, "ROOT", self.directory), patch.object(runner.subprocess, "run", execute), contextlib.redirect_stdout(output):
            result = runner.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 26)
        self.assertIn("25 passed; 1 failed", output.getvalue())
        self.assertIn("empty body", output.getvalue())


if __name__ == "__main__":
    unittest.main()
