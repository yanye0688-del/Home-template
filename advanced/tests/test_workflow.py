import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import memorykit as m
import encrypted_backup as backup


def args(**values):
    return argparse.Namespace(**values)


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ["identity.md", "baton.md", "standing.md", "last.txt"]:
            (self.root / name).write_text("Synthetic " + name)
        self.exports = self.root / "exports"
        self.exports.mkdir()
        self.write_export("surface", {"items": [{"id": "sample", "content": "Exact example"}]})
        self.write_export("letters", {"items": [{"id": "letter", "content": "Synthetic letter"}]})
        self.write_export("memories", {"items": [{"id": "sample", "content": "Exact example"}]})
        self.write_export("pins", {"items": [{"id": "sample", "content": "Exact example", "pinned": True, "resolved": True}]})
        self.write_export("self", {"entries": [{"id": "self-" + str(i), "content": "Full body " + str(i)} for i in range(27)]})
        adapter = [sys.executable, str(SCRIPTS / "export-adapter.py"), "--exports", str(self.exports)]
        config = {"workspace_root": ".", "files": {"identity": "identity.md", "baton": "baton.md", "long_term": "standing.md"},
                  "last_words_file": "last.txt", "adapters": {x: adapter for x in ["surface", "letters", "self", "recall", "pins"]},
                  "backup": {"sources": ["identity.md", "standing.md"]}}
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps(config))
        self.kit = m.Kit(self.config)

    def tearDown(self):
        self.temp.cleanup()

    def write_export(self, name, data):
        (self.exports / (name + ".json")).write_text(json.dumps(data))

    def orient(self, session="new"):
        result = m.orientation_export(self.kit, session, "sample")
        m.confirm_orientation(self.kit, session, True)
        return result

    def step(self, action, session="new", nonce=None, confirm=False):
        return m.handoff(self.kit, args(action=action, session=session, nonce=nonce, confirm=confirm, facts="facts.json"))

    def prepared(self):
        (self.root / "snapshot.bin").write_bytes(b"synthetic recoverable snapshot fixture")
        facts = {"memory_refs": ["sample"], "fixed_memory_changes": [],
                 "snapshot": {"path": "snapshot.bin", "sha256": m.digest((self.root / "snapshot.bin").read_bytes()), "restore_verified": True}}
        (self.root / "facts.json").write_text(json.dumps(facts))
        return self.step("prepare", session="old")["nonce"]

    def test_full_self_export_has_more_than_twenty(self):
        result = m.orientation_export(self.kit, "new", "sample")
        self.assertEqual(len(result["self"]["entries"]), 27)
        self.assertEqual(result["self"]["entries"][-1]["content"], "Full body 26")
        self.assertFalse(self.kit.read(m.session_name("new"))["confirmed_read"])

    def test_guard_needs_actual_explicit_confirmation(self):
        m.orientation_export(self.kit, "new", "sample")
        with self.assertRaises(m.KitError):
            m.run(self.kit, args(command="guard", session="new"))
        with self.assertRaises(m.KitError):
            m.confirm_orientation(self.kit, "new", False)
        self.orient()
        self.assertTrue(m.run(self.kit, args(command="guard", session="new"))["ready"])

    def test_changed_file_rejects_confirmation(self):
        m.orientation_export(self.kit, "new", "sample")
        (self.root / "baton.md").write_text("A changed scene")
        with self.assertRaises(m.KitError):
            m.confirm_orientation(self.kit, "new", True)

    def test_self_snapshot_change_while_paging_rejected(self):
        original = self.kit.adapter
        def moving(op, **kw):
            result = original(op, **kw)
            if op == "self" and kw["offset"] == 0:
                self.write_export("self", {"entries": [{"id": "different", "content": "new"}]})
            return result
        with patch.object(self.kit, "adapter", side_effect=moving), self.assertRaises(m.KitError):
            self.kit.all_self()

    def test_duplicate_self_ids_rejected(self):
        self.write_export("self", {"entries": [{"id": "same", "content": "a"}, {"id": "same", "content": "b"}]})
        with self.assertRaises(m.KitError):
            self.kit.all_self()

    def test_missing_letters_does_not_create_ready_receipt(self):
        (self.exports / "letters.json").unlink()
        with self.assertRaises(m.KitError):
            m.orientation_export(self.kit, "new", "sample")
        self.assertIsNone(self.kit.read(m.session_name("new")))

    def test_handoff_requires_new_window_before_retirement(self):
        nonce = self.prepared()
        with self.assertRaises(m.KitError):
            self.step("retire", session="old", nonce=nonce, confirm=True)
        with self.assertRaises(m.KitError):
            self.step("claim", session="old", nonce=nonce)
        self.step("claim", nonce=nonce)
        self.orient()
        verified = self.step("verify", nonce=nonce)
        self.assertTrue(verified["safe_to_retire_old"])
        self.assertFalse(verified["old_session_retired"])
        self.assertEqual(self.step("retire", session="old", nonce=nonce, confirm=True)["state"], "retired")

    def test_handoff_failed_self_check_keeps_old(self):
        nonce = self.prepared()
        self.step("claim", nonce=nonce)
        with self.assertRaises(m.KitError):
            self.step("verify", nonce=nonce)
        state = self.kit.read("handoff.json")
        self.assertEqual(state["state"], "failed")
        self.assertFalse(state["safe_to_retire_old"])
        self.assertFalse(state["old_session_retired"])

    def test_handoff_detects_snapshot_change(self):
        nonce = self.prepared();self.step("claim", nonce=nonce);self.orient()
        (self.root / "snapshot.bin").write_bytes(b"changed fixture")
        with self.assertRaises(m.KitError):
            self.step("verify", nonce=nonce)
        self.assertEqual(self.kit.read("handoff.json")["state"], "failed")

    def test_handoff_detects_changed_exact_memory(self):
        nonce = self.prepared();self.step("claim", nonce=nonce);self.orient()
        self.write_export("memories", {"items": [{"id": "sample", "content": "different"}]})
        with self.assertRaises(m.KitError):
            self.step("verify", nonce=nonce)

    def test_nonce_and_stale_orientation_rejected(self):
        nonce = self.prepared()
        with self.assertRaises(m.KitError):
            self.step("claim", nonce="wrong")
        self.orient();self.step("claim", nonce=nonce)
        with self.assertRaises(m.KitError):
            self.step("verify", nonce=nonce)

    def test_compaction_watermarks_are_once_per_epoch(self):
        def run(percent, epoch="0"):
            return m.run(self.kit, args(command="compact", session="s", epoch=epoch, percent=percent))
        self.assertEqual(run(70)["thresholds"], [65])
        self.assertFalse(run(70)["warning"])
        self.assertEqual(run(85)["thresholds"], [80])
        self.assertEqual(run(85, "1")["thresholds"], [65, 80])
        with self.assertRaises(m.KitError):run(float("nan"))

    def test_pin_check_uses_real_export_not_pinned_flag(self):
        self.assertTrue(m.run(self.kit, args(command="pin-check", id="sample"))["surfaced"])
        self.write_export("surface", {"items": []})
        with self.assertRaises(m.KitError):m.run(self.kit, args(command="pin-check", id="sample"))
        self.assertEqual(m.run(self.kit, args(command="digest"))["changed"], [])

    def test_reminder_is_idempotent_and_never_auto_delivered(self):
        event = args(command="remind", action="add", id="reminder-demo", at="2000-01-01T00:00:00+00:00", text="Synthetic reminder", confirm=False)
        m.run(self.kit, event);m.run(self.kit, event)
        self.assertEqual(len(self.kit.read("reminders.json")), 1)
        due = m.run(self.kit, args(command="remind", action="due"))
        self.assertEqual(len(due["items"]), 1)
        self.assertFalse(due["delivery_performed_by_script"])
        with self.assertRaises(m.KitError):m.run(self.kit, args(command="remind", action="done", id=event.id, confirm=False))
        m.run(self.kit, args(command="remind", action="done", id=event.id, confirm=True))
        self.assertEqual(self.kit.read("reminders.json")[0]["state"], "done")

    def test_reminder_naive_time_and_conflicting_id_rejected(self):
        with self.assertRaises(m.KitError):m.run(self.kit, args(command="remind", action="add", id="x", at="2030-01-01T00:00:00", text="x"))
        event = args(command="remind", action="add", id="x", at="2030-01-01T00:00:00+00:00", text="one")
        m.run(self.kit, event);event.text="two"
        with self.assertRaises(m.KitError):m.run(self.kit, event)

    def test_paths_and_private_receipts(self):
        with self.assertRaises(m.KitError):self.kit.path("../outside")
        with self.assertRaises(m.KitError):self.kit.path(".git/config")
        (self.root / "alias").symlink_to(self.root / "identity.md")
        with self.assertRaises(m.KitError):self.kit.path("alias")
        m.orientation_export(self.kit, "new", "sample")
        self.assertEqual((self.kit.state / m.session_name("new")).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.kit.state.stat().st_mode & 0o777, 0o700)

    def test_recall_query_never_becomes_a_shell(self):
        marker = self.root / "must-not-exist"
        result = m.run(self.kit, args(command="recall", query="$(touch " + str(marker) + ")"))
        self.assertEqual(result["items"], [])
        self.assertFalse(marker.exists())

    def test_bloat_is_metadata_only(self):
        self.kit.config.update(bloat_paths=["identity.md"], bloat_warning_bytes=1)
        result = m.run(self.kit, args(command="bloat"))
        self.assertEqual(result["oversized"], ["identity.md"])
        self.assertEqual(result["deleted"], [])
        self.assertNotIn("Synthetic", json.dumps(result))

    def test_read_only_adapter_cannot_pretend_to_write(self):
        with self.assertRaises(m.KitError):self.kit.adapter("note", text="Synthetic", operation_id="one")

    def test_hook_blocks_until_confirmed_then_warns_once(self):
        spec = importlib.util.spec_from_file_location("hook_bridge", SCRIPTS / "hook-bridge.py")
        hook = importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)
        event = {"hook_event_name": "Stop", "session_id": "new"}
        self.assertEqual(hook.handle(self.kit, event)["decision"], "block")
        self.orient()
        self.assertEqual(hook.handle(self.kit, event), {})
        event["context_usage_percent"] = 70
        self.assertEqual(hook.handle(self.kit, event)["decision"], "block")
        self.assertEqual(hook.handle(self.kit, event), {})
        start = hook.handle(self.kit, {"hook_event_name": "SessionStart", "session_id": "new"})
        self.assertIn("Synthetic letter", json.dumps(start))


class UploadAndLint(unittest.TestCase):
    def test_public_repository_refused_before_cipher_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fixture.gpg";p.write_bytes(b"synthetic ciphertext")
            calls = []
            def request(url, token, payload=None):calls.append(payload);return {"private": False}
            with self.assertRaises(m.KitError):backup.upload_private(p, {"repository": "example/private", "branch": "backup"}, "fixture", request)
            self.assertEqual(calls, [None])

    def test_private_upload_contains_only_ciphertext_and_hash_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"fixture.gpg";data=b"synthetic ciphertext";p.write_bytes(data);sent=[]
            def request(url, token, payload=None):
                if payload is None:return {"private": True}
                sent.append(payload)
                return {"content": {"sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}}
            result=backup.upload_private(p,{"repository":"example/private","branch":"backup"},"fixture",request)
            self.assertTrue(result["uploaded"])
            self.assertEqual(base64.b64decode(sent[0]["content"]), data)
            self.assertNotIn("sha", sent[0])

    def test_audit_reports_location_not_secret(self):
        spec=importlib.util.spec_from_file_location("audit",SCRIPTS/"audit-template.py");audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);secret="test-"+"z"*32;(p/"bad.txt").write_text("api_key='"+secret+"'")
            issues=audit.scan(p);self.assertTrue(issues);self.assertNotIn(secret,json.dumps(issues))


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgconf"), "GnuPG not installed; encryption path needs a separate check")
class GPG(unittest.TestCase):
    setUp = Workflow.setUp
    tearDown = Workflow.tearDown
    write_export = Workflow.write_export
    def test_encrypted_snapshot_decrypts_with_manifest(self):
        gpg_home=self.root/"gpg";gpg_home.mkdir(mode=0o700)
        try:
            subprocess.run(["gpg","--homedir",str(gpg_home),"--batch","--pinentry-mode","loopback","--passphrase","","--quick-generate-key","MemoryKit Test <memorykit@example.invalid>","rsa2048","encr","1d"],capture_output=True,timeout=60,check=True)
            keys=subprocess.run(["gpg","--homedir",str(gpg_home),"--with-colons","--list-keys"],capture_output=True,text=True,check=True).stdout
            fingerprint=next(line.split(":")[9] for line in keys.splitlines() if line.startswith("fpr:"))
            with patch.dict(os.environ,{"GNUPGHOME":str(gpg_home)}):path,report=backup.create_backup(self.kit,fingerprint)
            self.assertFalse(report["restore_verified"]);self.assertNotIn(b"Synthetic",path.read_bytes())
            plain=subprocess.run(["gpg","--homedir",str(gpg_home),"--batch","--decrypt",str(path)],capture_output=True,check=True).stdout
            with tarfile.open(fileobj=io.BytesIO(plain),mode="r:gz") as tar:
                manifest=json.load(tar.extractfile("memorykit-manifest.json"))
                for name,expected in manifest["files"].items():self.assertEqual(m.digest(tar.extractfile(name).read()),expected)
        finally:
            subprocess.run(["gpgconf","--homedir",str(gpg_home),"--kill","gpg-agent"],capture_output=True)


if __name__ == "__main__":unittest.main()
