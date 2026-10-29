#!/usr/bin/env python3
"""Encrypt explicit stable exports locally; upload only on an explicit request."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from memorykit import Kit, KitError, atomic_json, digest


def request_json(url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, method="PUT" if data is not None else "GET",
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/vnd.github+json",
                               "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def upload_private(path, settings, token, request=request_json):
    repository = settings.get("repository", "")
    branch = settings.get("branch", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[A-Za-z0-9_.-]+", branch) or not token:
        raise KitError("explicit private repository, existing branch and token environment variable are required")
    if path.suffix != ".gpg" or path.stat().st_size > 20 * 1024 * 1024:
        raise KitError("only an encrypted .gpg snapshot up to 20 MiB may be uploaded")
    root = "https://api.github.com/repos/" + repository
    if request(root, token).get("private") is not True:
        raise KitError("repository is not confirmed private; nothing uploaded")
    data = path.read_bytes()
    # No 'sha' field: never overwrite an existing path, force-push or delete.
    result = request(root + "/contents/encrypted-snapshots/" + path.name, token,
                     {"message": "Add encrypted memory snapshot", "branch": branch,
                      "content": base64.b64encode(data).decode()})
    expected = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if result.get("content", {}).get("sha") != expected:
        raise KitError("uploaded ciphertext hash was not confirmed; inspect before retrying")
    return {"uploaded": True, "private_checked": True}


def create_backup(kit, recipient, gpg="gpg"):
    if not re.fullmatch(r"[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64}", recipient):
        raise KitError("use an explicit full public-key fingerprint")
    sources = list(kit.config.get("backup", {}).get("sources", []))
    if kit.config.get("adapters", {}).get("backup_export"):
        export = kit.adapter("backup_export")
        path = kit.path(export["path"])
        if digest(path.read_bytes()) != export.get("sha256"):
            raise KitError("backend export hash mismatch")
        sources.append(export["path"])
    if not sources:
        raise KitError("choose explicit stable files or a consistent backend export first")
    paths = []
    for name in sources:
        path = kit.path(name)
        if not path.is_file() or not path.stat().st_size:
            raise KitError("backup sources must be non-empty stable files")
        if path.name == ".env" or path.suffix.lower() in (".key", ".pem", ".token", ".db", ".sqlite", ".sqlite3"):
            raise KitError("credentials and live database files are not backup inputs; use backend export")
        paths.append(path)
    destination = kit.state / "backups"
    destination.mkdir(mode=0o700, exist_ok=True)
    if destination.is_symlink():
        raise KitError("backup directory must not be a symlink")
    destination.chmod(0o700)
    out = destination / ("snapshot-" + str(time.time_ns()) + "-" + secrets.token_hex(4) + ".tar.gz.gpg")
    with tempfile.TemporaryDirectory(prefix=".backup-", dir=kit.state) as temp:
        archive = Path(temp) / "snapshot.tar.gz"
        manifest = {str(p.relative_to(kit.root)): digest(p.read_bytes()) for p in paths}
        with tarfile.open(archive, "w:gz") as tar:
            for path in paths:
                if str(path.relative_to(kit.root)) == "memorykit-manifest.json":
                    raise KitError("reserved archive manifest name")
                tar.add(path, arcname=str(path.relative_to(kit.root)), recursive=False)
            data = json.dumps({"format": 1, "files": manifest}, sort_keys=True).encode()
            info = tarfile.TarInfo("memorykit-manifest.json")
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
        if any(digest(p.read_bytes()) != manifest[str(p.relative_to(kit.root))] for p in paths):
            raise KitError("backup source changed while packing")
        # No shell and no trust bypass; untrusted/missing recipient keys fail.
        try:
            subprocess.run([gpg, "--batch", "--yes", "--output", str(out), "--encrypt", "--recipient", recipient, str(archive)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120, check=True)
        except (OSError, subprocess.SubprocessError):
            out.unlink(missing_ok=True)
            raise KitError("encryption failed; inspect your local GPG setup") from None
    out.chmod(0o600)
    report = {"path": str(out.relative_to(kit.root)), "sha256": digest(out.read_bytes()),
              "source_sha256": manifest, "uploaded": False, "restore_verified": False}
    atomic_json(out.with_suffix(out.suffix + ".json"), report)
    return out, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    try:
        kit = Kit(args.config)
        with kit.lock():
            path, result = create_backup(kit, args.recipient)
            if args.upload:
                settings = kit.config.get("backup", {})
                result.update(upload_private(path, settings, os.environ.get(settings.get("token_env", "GITHUB_TOKEN"), "")))
        print(json.dumps(result))
        return 0
    except (KitError, OSError, ValueError, KeyError, HTTPError):
        print("Backup/upload did not complete. Keep any local ciphertext; inspect locally, do not retry blindly.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
