import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/validate_readme_commands.py'
spec = importlib.util.spec_from_file_location('validator', SCRIPT)
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


class ReadmeValidatorTest(unittest.TestCase):
    def test_reads_shell_examples_only(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / 'README.md'
            readme.write_text('```yaml\nkey: value\n```\n```shell\necho hello\n```\n')
            self.assertEqual(validator.read_commands(readme), ['echo hello'])

    def test_unterminated_or_empty_readme_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / 'README.md'
            readme.write_text('```shell\necho hello\n')
            with self.assertRaisesRegex(ValueError, 'unterminated'):
                validator.read_commands(readme)
            readme.write_text('No commands here')
            with self.assertRaisesRegex(ValueError, 'no shell commands'):
                validator.read_commands(readme)

    def test_finds_readme_shell_blocks(self):
        commands = validator.read_commands(Path(__file__).resolve().parents[1] / 'README.md')
        self.assertIn('./demo.sh start', commands)
        self.assertIn('./scenarios/05-status-before-lint.sh', commands)

    def test_stop_server_falls_back_when_process_group_signal_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            instance = validator.Validator(Path(directory), timeout=1)
            process = subprocess.Popen(
                [sys.executable, '-c', 'import time; time.sleep(30)'],
                start_new_session=True)
            instance.server = process
            try:
                with patch.object(validator.os, 'killpg', side_effect=PermissionError(1, 'Operation not permitted')):
                    instance.stop_server()
                self.assertIsNotNone(process.poll())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
