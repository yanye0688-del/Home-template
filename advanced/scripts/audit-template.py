#!/usr/bin/env python3
"""Local release lint. Reports locations/categories, never matched secret values."""
import argparse
import ipaddress
import json
from pathlib import Path
import re

RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY"),
    "credential_literal": re.compile(r'''(?i)(?:api[_-]?key|token|secret|password|pin)\s*[=:]\s*["']([A-Za-z0-9_./+=-]{20,})["']'''),
    "machine_home_path": re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
    "possible_private_memory_id": re.compile(r"\b[a-f0-9]{12}\b"),
}
FORBIDDEN = {".git", ".env", ".memorykit-state", "private-exports", "buckets-data", "relay.db", "__pycache__"}


def scan(root):
    issues = []
    for path in sorted(root.rglob("*")):
        name = str(path.relative_to(root))
        if path.is_symlink():
            issues.append({"file": name, "rule": "symlink"});continue
        if any(part in FORBIDDEN for part in path.relative_to(root).parts):
            issues.append({"file": name, "rule": "runtime_or_private_artifact"});continue
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeError:
            issues.append({"file": name, "rule": "non_text_artifact"});continue
        for number, line in enumerate(text.splitlines(), 1):
            for rule, pattern in RULES.items():
                if pattern.search(line):
                    issues.append({"file": name, "line": number, "rule": rule})
            for candidate in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line):
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not address.is_loopback:
                    issues.append({"file": name, "line": number, "rule": "literal_network_address"})
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    issues = scan(args.directory)
    print(json.dumps({"passed": not issues, "issues": issues}, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
