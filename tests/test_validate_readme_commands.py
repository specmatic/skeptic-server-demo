import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/validate_readme_commands.py'
spec = importlib.util.spec_from_file_location('validator', SCRIPT)
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


class ReadmeValidatorTest(unittest.TestCase):
    def test_indented_blocks_and_missing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / 'README.md'
            readme.write_text('   ```shell\n   echo hello\n   ```\n\n   ```terminaloutput\n   hello\n   ```\n')
            commands = validator.parse_readme(readme)
            self.assertEqual(commands[0].command, 'echo hello')
            self.assertEqual(commands[0].expected, 'hello')
            readme.write_text('```shell\necho hello\n```\n')
            with self.assertRaises(ValueError):
                validator.parse_readme(readme)

    def test_types_order_and_request_id_consistency(self):
        expected = '''=== Request ===
GET https://localhost:8443/health
=== Response ===
HTTP/2 400
x-request-id: <request-id: UUID>
{"code":"INVALID_REQUEST","requestId":"<request-id: UUID>"}'''
        actual = '''=== Request ===
GET https://localhost:8443/health
=== Response ===
HTTP/2 400
x-request-id: 12345678-1234-4234-8234-123456789abc
content-type: application/json
{"requestId":"12345678-1234-4234-8234-123456789abc","code":"INVALID_REQUEST"}'''
        validator.match_output(expected, actual)
        for changed in (actual.replace('HTTP/2 400', 'HTTP/2 200'),
                        actual.replace('12345678-1234-4234-8234-123456789abc', 'invalid'),
                        actual.replace('"requestId":"12345678', '"requestId":"22345678')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validator.match_output(expected, changed)

    def test_requests_have_separate_placeholder_bindings(self):
        expected = '=== Request ===\nX-Request-Id: <request-id: UUID>\n'
        validator.match_output(expected * 2,
                               '=== Request ===\nX-Request-Id: 12345678-1234-4234-8234-123456789abc\n'
                               '=== Request ===\nX-Request-Id: 22345678-1234-4234-8234-123456789abc\n')

    def test_json_body_and_numeric_templates(self):
        validator.match_output('<request-body: JSON object from the scenario fixture>\n'
                               '{"attempts": <attempt-count: positive integer>}',
                               '{\n "config": {}\n}\n{"attempts": 2}')
        for output in ('[]\n{"attempts": 2}', '{}\n{"attempts": 0}', '{}\n{"attempts": "2"}'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                validator.match_output('<request-body: JSON object from the scenario fixture>\n'
                                       '{"attempts": <attempt-count: positive integer>}', output)

    def test_placeholder_formats(self):
        cases = [('UUID', '12345678-1234-4234-8234-123456789abc', 'no'),
                 ('ISO 8601 date-time, UTC', '2026-11-07T08:49:50.333Z', '2026-99-07T08:49:50Z'),
                 ('40 hexadecimal characters', 'a' * 40, 'z' * 40),
                 ('positive integer', '42', '0'),
                 ('non-negative integer, bytes', '0', '-1'),
                 ('yyyyMMdd-HHmmss', '20261107-134044', '20269907-134044'),
                 ('absolute path', '/tmp/demo', 'relative/path')]
        for kind, good, bad in cases:
            with self.subTest(kind=kind):
                validator.match_output(f'<value: {kind}>', good)
                with self.assertRaises(ValueError):
                    validator.match_output(f'<value: {kind}>', bad)
        with self.assertRaises(ValueError):
            validator.match_output('<value: unsupported>', 'anything')

    def test_adjacent_typed_placeholders(self):
        validator.match_output('session-<time: yyyyMMdd-HHmmss>-<pid: positive integer>',
                               'session-20261107-143424-11581')

    def test_timeout_stops_owned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = validator.Runner(Path(directory), 0.1)
            try:
                with self.assertRaisesRegex(ValueError, 'timed out'):
                    runner.run('sleep 30 & wait')
                self.assertTrue(all(proc.poll() is not None for proc in runner.processes))
            finally:
                runner.close()

    def test_missing_or_unknown_templates_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            for text in ('```shell\necho hello\n',
                         '```shell\necho hello\n```\n```terminaloutput\n<value: unknown>\n```'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    validator.parse_readme(path)
        with self.assertRaises(ValueError):
            validator.match_output('first\nsecond', 'second\nfirst')

    def test_status_arrays_and_return_codes(self):
        with self.assertRaises(ValueError):
            validator.match_output('{"configs": []}', '{"configs": [{"stale": true}]}')
        self.assertEqual(validator.expected_exit("SPECMATIC_LICENSE_CONTENT='this-is-not-a-valid-license' ./demo.sh start"), 1)
        self.assertEqual(validator.expected_exit('./scenarios/03-no-token-401.sh'), 0)


if __name__ == '__main__':
    unittest.main()
