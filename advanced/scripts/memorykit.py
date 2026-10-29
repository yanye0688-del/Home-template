#!/usr/bin/env python3
"""Opt-in local memory workflow. No model calls, process killing or auto delivery."""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime


class KitError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def atomic_json(path, value):
    if path.is_symlink():
        raise KitError("state file must not be a symlink")
    fd, name = tempfile.mkstemp(prefix=".memorykit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Kit:
    def __init__(self, config):
        config = Path(config).resolve()
        self.config = json.loads(config.read_text())
        if not isinstance(self.config, dict):
            raise KitError("configuration must be a JSON object")
        self.root = (config.parent / self.config.get("workspace_root", ".")).resolve()
        if not self.root.is_dir():
            raise KitError("workspace_root must already exist")
        self.state = self.path(self.config.get("state_dir", ".memorykit-state"))
        if self.state == self.root:
            raise KitError("state_dir must be a dedicated child directory")
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state.chmod(0o700)

    def path(self, name):
        raw = self.root / name
        if ".git" in raw.parts or any(p.is_symlink() for p in [raw, *raw.parents] if p != self.root.parent):
            raise KitError("symlinks and .git are outside this workflow")
        resolved = raw.resolve()
        if not resolved.is_relative_to(self.root):
            raise KitError("path escapes workspace_root")
        return resolved

    @contextlib.contextmanager
    def lock(self):
        path = self.state / ".lock"
        if path.is_symlink():
            raise KitError("lock must not be a symlink")
        with path.open("a") as stream:
            path.chmod(0o600)
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self, name, default=None):
        path = self.state / name
        if path.is_symlink():
            raise KitError("state file must not be a symlink")
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, name, data):
        atomic_json(self.state / name, data)

    def adapter(self, operation, **params):
        argv = self.config.get("adapters", {}).get(operation)
        if not isinstance(argv, list) or not argv or any(not isinstance(s, str) or not s or "<" in s for s in argv):
            raise KitError("adapter is not configured: " + operation)
        # Runtime text goes to stdin as data; never interpolate it into a shell.
        try:
            result = subprocess.run(argv, input=canonical({"operation": operation, **params}),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=60, check=False, cwd=self.root)
        except (OSError, subprocess.TimeoutExpired):
            raise KitError("adapter unavailable: " + operation) from None
        if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
            raise KitError("adapter failed or exceeded output bound: " + operation)
        try:
            value = json.loads(result.stdout)
        except (UnicodeError, ValueError):
            raise KitError("adapter must return one JSON value: " + operation) from None
        if not isinstance(value, dict):
            raise KitError("adapter result must be an object")
        return value

    def files(self):
        result = {}
        for role in ("identity", "baton", "long_term"):
            name = self.config.get("files", {}).get(role)
            if not isinstance(name, str):
                raise KitError("missing required file role: " + role)
            data = self.path(name).read_bytes()
            if not data.strip():
                raise KitError("required file is empty: " + role)
            result[role] = {"path": name, "sha256": digest(data)}
        return result

    def all_self(self):
        offset, entries, ids, snapshot, total = 0, [], set(), None, None
        while True:
            page = self.adapter("self", offset=offset, limit=5)
            if not re.fullmatch(r"[a-f0-9]{64}", str(page.get("snapshot_sha256", ""))):
                raise KitError("self export needs a snapshot_sha256")
            if type(page.get("total")) is not int or page["total"] < 0:
                raise KitError("invalid self export count")
            if snapshot is None:
                snapshot, total = page["snapshot_sha256"], page["total"]
            if snapshot != page["snapshot_sha256"] or total != page["total"]:
                raise KitError("self export changed while paging; read it again")
            batch = page.get("entries")
            if not isinstance(batch, list):
                raise KitError("self export entries must be a list")
            for entry in batch:
                if not isinstance(entry, dict) or not isinstance(entry.get("content"), str) or not isinstance(entry.get("id"), str) or entry["id"] in ids:
                    raise KitError("invalid or duplicate self entry")
                ids.add(entry["id"])
                entries.append(entry)
            next_offset = page.get("next_offset")
            if next_offset is None:
                if len(entries) != total:
                    raise KitError("self export is incomplete")
                return {"snapshot_sha256": snapshot, "total": total, "entries": entries}
            if not batch or type(next_offset) is not int or next_offset != offset + len(batch) or next_offset > total:
                raise KitError("invalid self export cursor")
            offset = next_offset


def session_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise KitError("invalid session id")
    return "orientation-" + digest(value.encode())[:24] + ".json"


def items(value):
    rows = value.get("items")
    if not isinstance(rows, list) or any(not isinstance(x, dict) or not isinstance(x.get("id"), str) or not isinstance(x.get("content"), str) for x in rows):
        raise KitError("adapter items require string id and full content")
    return rows


def orientation_export(kit, session, sample):
    files = kit.files()
    # Read identity first, then surfacing, letters, baton, standing memory, full self.
    surfaced = items(kit.adapter("surface"))
    letters = items(kit.adapter("letters", limit=6))
    self_data = kit.all_self()
    recalled = kit.adapter("recall", id=sample)
    if recalled.get("id") != sample or not isinstance(recalled.get("content"), str) or not recalled["content"].strip():
        raise KitError("exact sample could not be recalled")
    receipt = {"session": session, "files": files, "exported_at": time.time(),
               "self_snapshot": self_data["snapshot_sha256"], "self_total": self_data["total"],
               "sample_id": sample, "sample_sha256": digest(recalled["content"].encode()),
               "confirmed_read": False}
    kit.write(session_name(session), receipt)
    return {"identity": kit.path(files["identity"]["path"]).read_text(), "surface": surfaced,
            "letters": letters, "baton": kit.path(files["baton"]["path"]).read_text(),
            "long_term": kit.path(files["long_term"]["path"]).read_text(), "self": self_data,
            "sample": recalled, "receipt": session_name(session),
            "note": "Export integrity is not proof of understanding. Read all bodies before confirming."}


def confirm_orientation(kit, session, confirm):
    if not confirm:
        raise KitError("explicit --confirm-read is required after reading every body")
    receipt = kit.read(session_name(session))
    if not receipt or receipt["session"] != session or receipt["files"] != kit.files():
        raise KitError("orientation missing or required files changed")
    fresh = kit.adapter("self", offset=0, limit=1)
    if fresh.get("snapshot_sha256") != receipt["self_snapshot"] or fresh.get("total") != receipt["self_total"]:
        raise KitError("self knowledge changed; export and read again")
    receipt["confirmed_read"] = True
    kit.write(session_name(session), receipt)
    return {"ready": True, "session": session}


def handoff(kit, args):
    state = kit.read("handoff.json")
    if args.action == "prepare":
        if state and state["state"] not in ("failed", "retired"):
            raise KitError("an unfinished handoff already exists")
        facts = json.loads(kit.path(args.facts).read_text())
        if not isinstance(facts.get("memory_refs"), list) or not facts["memory_refs"] or not all(isinstance(x, str) and x for x in facts["memory_refs"]):
            raise KitError("important memory references are required")
        if not isinstance(facts.get("fixed_memory_changes"), list):
            raise KitError("fixed_memory_changes must explicitly be a list, even when empty")
        snap = facts.get("snapshot", {})
        path = kit.path(snap["path"])
        if not path.is_file() or not path.stat().st_size or digest(path.read_bytes()) != snap.get("sha256") or snap.get("restore_verified") is not True:
            raise KitError("verified recoverable snapshot is required")
        state = {"state": "prepared", "old_session": args.session, "nonce": secrets.token_hex(16),
                 "prepared_at": time.time(), "files": kit.files(), "facts": facts,
                 "safe_to_retire_old": False, "old_session_retired": False}
    else:
        if not state or args.nonce != state["nonce"]:
            raise KitError("handoff nonce mismatch or state missing")
        if args.action == "claim":
            if state["state"] != "prepared" or args.session == state["old_session"]:
                raise KitError("a different new session must claim a prepared handoff")
            state.update(state="candidate", new_session=args.session, claimed_at=time.time())
        elif args.action == "verify":
            try:
                if state["state"] != "candidate" or state["new_session"] != args.session:
                    raise KitError("candidate session mismatch")
                receipt = kit.read(session_name(args.session)) or {}
                snap = state["facts"]["snapshot"]
                if not receipt.get("confirmed_read") or receipt.get("files") != kit.files() or receipt["files"] != state["files"] or receipt.get("exported_at", 0) < state["claimed_at"]:
                    raise KitError("new session has not completed a fresh orientation")
                if receipt.get("sample_id") != state["facts"]["memory_refs"][0] or not receipt.get("sample_sha256"):
                    raise KitError("important memory sample missing")
                fresh = kit.adapter("self", offset=0, limit=1)
                recalled = kit.adapter("recall", id=receipt["sample_id"])
                if fresh.get("snapshot_sha256") != receipt["self_snapshot"] or fresh.get("total") != receipt["self_total"] or recalled.get("id") != receipt["sample_id"] or digest(recalled.get("content", "").encode()) != receipt["sample_sha256"]:
                    raise KitError("memory changed since the confirmed export")
                if digest(kit.path(snap["path"]).read_bytes()) != snap["sha256"]:
                    raise KitError("snapshot changed")
                state.update(state="verified", safe_to_retire_old=True)
            except (KitError, OSError, KeyError) as error:
                state.update(state="failed", safe_to_retire_old=False)
                kit.write("handoff.json", state)
                raise KitError("verification failed; keep using the old session") from error
        elif args.action == "retire":
            if state["state"] != "verified" or not args.confirm:
                raise KitError("verify first, then explicitly confirm retirement")
            state.update(state="retired", old_session_retired=True)
        elif args.action == "fail":
            if state["state"] == "retired":
                raise KitError("cannot undo a recorded retirement automatically")
            state.update(state="failed", safe_to_retire_old=False)
    kit.write("handoff.json", state)
    # This helper records a protocol. It never kills or launches a process.
    return {k: state[k] for k in ("state", "nonce", "safe_to_retire_old", "old_session_retired")}


def run(kit, args):
    if args.command == "orientation":
        if args.action == "export":
            return orientation_export(kit, args.session, args.sample)
        return confirm_orientation(kit, args.session, args.confirm_read)
    if args.command == "guard":
        receipt = kit.read(session_name(args.session), {})
        if not receipt.get("confirmed_read"):
            raise KitError("read the full orientation export before the first final reply")
        return {"ready": True}
    if args.command == "handoff":
        return handoff(kit, args)
    if args.command == "letters":
        last = kit.config.get("last_words_file")
        return {"letters": items(kit.adapter("letters", limit=6)),
                "last_words": kit.path(last).read_text() if last else None}
    if args.command == "compact":
        if not math.isfinite(args.percent) or not 0 <= args.percent <= 100:
            raise KitError("context percentage must be finite and between 0 and 100")
        key = "compact-" + digest((args.session + ":" + args.epoch).encode())[:24] + ".json"
        seen = kit.read(key, [])
        thresholds = kit.config.get("compact_thresholds", [65, 80])
        if not isinstance(thresholds, list) or any(type(x) is not int or not 0 < x <= 100 for x in thresholds):
            raise KitError("compact_thresholds must be percentages")
        crossed = [x for x in sorted(set(thresholds)) if args.percent >= x and x not in seen]
        kit.write(key, sorted(set(seen + crossed)))
        return {"warning": bool(crossed), "thresholds": crossed,
                "message": "Save a checkpoint; this is a local early-warning threshold, not a platform compaction limit." if crossed else ""}
    if args.command == "pin-check":
        found = any(row["id"] == args.id for row in items(kit.adapter("surface")))
        if not found:
            raise KitError("pinned item did not appear in a real surfacing call")
        return {"surfaced": True, "id": args.id}
    if args.command == "digest":
        rows = items(kit.adapter("pins"))
        return {"mode": "review_only", "candidates": [x["id"] for x in rows if x.get("pinned") and x.get("resolved") and not x.get("protected")], "changed": []}
    if args.command == "recall":
        return kit.adapter("recall", query=args.query)
    if args.command == "note":
        result = kit.adapter("note", text=args.text, operation_id=args.operation_id)
        recalled = kit.adapter("recall", id=result["id"])
        if recalled.get("content") != args.text:
            raise KitError("write may have happened, but exact readback did not match; do not retry blindly")
        return {"id": result["id"], "verified_exact": True}
    if args.command == "remind":
        ledger = kit.read("reminders.json", [])
        if args.action == "add":
            at = datetime.fromisoformat(args.at)
            if at.utcoffset() is None:
                raise KitError("reminder time needs an explicit timezone")
            record = {"id": args.id, "at": at.isoformat(), "text": args.text, "state": "pending"}
            old = next((x for x in ledger if x["id"] == args.id), None)
            if old and {k: old[k] for k in ("id", "at", "text")} != {k: record[k] for k in ("id", "at", "text")}:
                raise KitError("operation id already belongs to another reminder")
            if not old:
                ledger.append(record)
        elif args.action == "done":
            if not args.confirm:
                raise KitError("confirm actual delivery before marking a reminder done")
            record = next((x for x in ledger if x["id"] == args.id), None)
            if not record:
                raise KitError("reminder id not found")
            record["state"] = "done"
        kit.write("reminders.json", ledger)
        return {"items": [x for x in ledger if args.action != "due" or x["state"] == "pending" and datetime.fromisoformat(x["at"]).timestamp() <= time.time()], "delivery_performed_by_script": False}
    if args.command == "bloat":
        files = []
        for name in kit.config.get("bloat_paths", []):
            path = kit.path(name)
            for p in ([path] if path.is_file() else path.rglob("*.md")):
                if p.is_file() and not p.is_symlink():
                    safe = kit.path(str(p.relative_to(kit.root)))
                    files.append({"path": str(safe.relative_to(kit.root)), "bytes": safe.stat().st_size})
        total = sum(x["bytes"] for x in files)
        return {"files": files, "total_bytes": total,
                "oversized": [x["path"] for x in files if x["bytes"] > kit.config.get("bloat_warning_bytes", 65536)],
                "total_warning": total > kit.config.get("bloat_total_warning_bytes", 1048576), "deleted": []}
    raise KitError("unknown command")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    sub = p.add_subparsers(dest="command", required=True)
    o = sub.add_parser("orientation");o.add_argument("action", choices=["export", "confirm"]);o.add_argument("--session", required=True);o.add_argument("--sample");o.add_argument("--confirm-read", action="store_true")
    g = sub.add_parser("guard");g.add_argument("--session", required=True)
    h = sub.add_parser("handoff");h.add_argument("action", choices=["prepare", "claim", "verify", "fail", "retire"]);h.add_argument("--session", required=True);h.add_argument("--facts");h.add_argument("--nonce");h.add_argument("--confirm", action="store_true")
    sub.add_parser("letters")
    c = sub.add_parser("compact");c.add_argument("--session", required=True);c.add_argument("--epoch", default="0");c.add_argument("--percent", required=True, type=float)
    pin = sub.add_parser("pin-check");pin.add_argument("id")
    sub.add_parser("digest")
    recall = sub.add_parser("recall");recall.add_argument("query")
    note = sub.add_parser("note");note.add_argument("--text", required=True);note.add_argument("--operation-id", required=True)
    r = sub.add_parser("remind");r.add_argument("action", choices=["add", "due", "list", "done"]);r.add_argument("--id");r.add_argument("--at");r.add_argument("--text");r.add_argument("--confirm", action="store_true")
    sub.add_parser("bloat")
    return p


def main(argv=None):
    p = parser();args = p.parse_args(argv)
    try:
        if args.command == "orientation" and args.action == "export" and not args.sample:
            raise KitError("--sample must be an exact existing memory id")
        if args.command == "handoff" and args.action == "prepare" and not args.facts:
            raise KitError("prepare requires --facts")
        if args.command == "remind" and (args.action == "add" and not all((args.id, args.at, args.text)) or args.action == "done" and not args.id):
            raise KitError("reminder fields missing")
        kit = Kit(args.config)
        with kit.lock():
            result = run(kit, args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (KitError, OSError, ValueError, KeyError) as error:
        # Do not print subprocess stderr, credentials, or arbitrary runtime values.
        message = str(error) if isinstance(error, KitError) else "local configuration or state could not be read; inspect it privately"
        print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
