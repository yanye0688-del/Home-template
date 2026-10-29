import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class CLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ["identity.md", "baton.md", "standing.md"]:
            (self.root / name).write_text("Synthetic fixture")
        config = {"workspace_root": ".", "files": {"identity": "identity.md", "baton": "baton.md", "long_term": "standing.md"}}
        self.path = self.root / "config.json"
        self.path.write_text(json.dumps(config))
        self.env = dict(os.environ, MEMORYKIT_CONFIG=str(self.path), PYTHONDONTWRITEBYTECODE="1")

    def tearDown(self):
        self.temp.cleanup()

    def test_shell_and_python_entrypoints_use_private_config(self):
        blocked = subprocess.run(["sh", str(SCRIPTS / "check-orientation.sh"), "--session", "fixture"], env=self.env, capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 2)
        first = subprocess.run([sys.executable, str(SCRIPTS / "check-compact-warning.py"), "--session", "fixture", "--percent", "70"], env=self.env, capture_output=True, text=True, check=True)
        second = subprocess.run([sys.executable, str(SCRIPTS / "check-compact-warning.py"), "--session", "fixture", "--percent", "70"], env=self.env, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(first.stdout)["warning"])
        self.assertFalse(json.loads(second.stdout)["warning"])

    def test_hook_reads_json_without_transcript_access(self):
        event = {"hook_event_name": "Stop", "session_id": "fixture", "transcript_path": "must-not-be-opened"}
        result = subprocess.run([sys.executable, str(SCRIPTS / "hook-bridge.py"), "--config", str(self.path)], input=json.dumps(event), env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertFalse((self.root / "must-not-be-opened").exists())


if __name__ == "__main__":
    unittest.main()
