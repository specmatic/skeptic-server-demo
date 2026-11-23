import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "demo.py"
spec = importlib.util.spec_from_file_location("demo", SCRIPT)
demo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = demo
spec.loader.exec_module(demo)


class DemoConfigTokenTest(unittest.TestCase):
    def test_token_is_request_field_and_never_url_userinfo(self):
        secret = "fixture-token-do-not-print"
        request = demo.build_lint_request("lint-clean-batch", secret)
        git = request["config"]["git"]
        self.assertEqual(git["url"], "https://github.com/specmatic/private-central-linter-config.git")
        self.assertEqual(git["token"], secret)
        self.assertNotIn(secret, git["url"])

    def test_public_request_omits_token_field(self):
        request = demo.build_lint_request("lint-clean-batch", None)
        self.assertNotIn("token", request["config"]["git"])

    def test_refresh_fixture_uses_clean_url_and_separate_token_field(self):
        token = "app-token-fixture"
        request = demo.build_lint_request("lint-config-refresh", token)
        self.assertEqual(request["config"]["git"]["url"],
                         "https://github.com/specmatic/private-central-linter-config.git")
        self.assertEqual(request["config"]["git"]["token"], token)
        self.assertEqual(request["repository"]["specifications"][0]["id"], "config-refresh-marker")

    def test_http_submission_keeps_token_out_of_url_and_files(self):
        secret = "fixture-token-do-not-print"
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "server-url").write_text("http://127.0.0.1:8000")
            (state / "good.jwt").write_text("demo-jwt")
            seen = {}

            class Response:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

                def read(self):
                    return b'{"result":"success","reports":[]}'

            def urlopen(request, **_):
                seen["url"] = request.full_url
                seen["body"] = json.loads(request.data)
                return Response()

            with patch.object(demo, "STATE", state), patch.dict("os.environ", {
                "DEMO_CONFIG_TOKEN": secret,
                "DEMO_CONFIG_REPO_URL": "https://github.com/example/private-test.git",
                "DEMO_CONFIG_BRANCH": "validation-only",
            }), patch.object(demo.urllib.request, "urlopen", side_effect=urlopen):
                status, _, sent_token = demo.send_lint_request("lint-clean-batch", "request-id")

            git = seen["body"]["config"]["git"]
            self.assertEqual(status, 200)
            self.assertEqual(sent_token, secret)
            self.assertEqual(git["token"], secret)
            self.assertEqual(git["url"], "https://github.com/example/private-test.git")
            self.assertEqual(git["branch"], "validation-only")
            self.assertNotIn(secret, seen["url"])
            self.assertEqual(list(state.iterdir()), [state / "good.jwt", state / "server-url"])

    def test_scenario_output_and_saved_response_do_not_contain_config_token(self):
        secret = "fixture-token-do-not-print"
        echoes = (secret.encode(), demo.quote(secret, safe="").encode(),
                  demo.base64.b64encode(f"x-access-token:{secret}".encode()))
        response = b'{"details":"' + b' '.join(echoes) + b'","code":"INVALID_CONFIG_TOKEN"}'
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "server-url").write_text("http://127.0.0.1:8000")
            output = io.StringIO()
            with patch.object(demo, "STATE", state), patch.dict("os.environ", {"DEMO_CONFIG_TOKEN": secret}), \
                    patch.object(demo, "send_lint_request", return_value=(422, response, secret)), \
                    contextlib.redirect_stdout(output):
                demo.post_scenario("lint-clean-batch", "Validation")
            self.assertNotIn(secret, output.getvalue())
            for path in state.iterdir():
                self.assertNotIn(secret.encode(), path.read_bytes())

    def test_cleanup_removes_only_known_generated_credentialed_request_files(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for name in ("lint-batch-authenticated.json", "lint-batch-invalid-config-token.json",
                         "other-authenticated.json",
                         "keep-this.json", "lint-batch-response.json"):
                (state / name).write_text("fixture")
            with patch.object(demo, "STATE", state), patch.object(sys, "argv", [str(SCRIPT), "cleanup-legacy-requests"]):
                demo.main()
            self.assertEqual({path.name for path in state.iterdir()},
                             {"other-authenticated.json", "keep-this.json", "lint-batch-response.json"})

    def test_assert_refresh_checks_sha_and_marker_rule(self):
        response = {
            "config": {"commitSha": "a" * 40},
            "reports": [{"sarifReport": {"runs": [{"results": [{
                "ruleId": "operation-summary",
                "message": {"text": "CLIENT_VALIDATION_C1"},
            }]}]}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json"
            path.write_text(json.dumps(response))
            demo.assert_refreshed_report(path, "a" * 40)
            response["reports"][0]["sarifReport"]["runs"][0]["results"][0]["ruleId"] = "different"
            path.write_text(json.dumps(response))
            with self.assertRaisesRegex(SystemExit, "missing operation-summary"):
                demo.assert_refreshed_report(path, "a" * 40)
            with self.assertRaisesRegex(SystemExit, "Expected config SHA"):
                demo.assert_refreshed_report(path, "b" * 40)


if __name__ == "__main__":
    unittest.main()
