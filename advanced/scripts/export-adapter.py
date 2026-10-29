#!/usr/bin/env python3
"""Read a deliberately prepared JSON export; does not access a backend or chats."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def read(root, name):
    path = root / (name + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing regular export")
    value = json.loads(path.read_text())
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.exports).resolve()
        request = json.load(sys.stdin)
        op = request["operation"]
        if op in ("surface", "letters", "pins"):
            result = read(root, op)
            if op == "letters":
                result = {"items": result["items"][:request.get("limit", 6)]}
        elif op == "self":
            rows = read(root, "self")["entries"]
            offset, limit = request["offset"], request["limit"]
            if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
                raise ValueError("bad page")
            end = min(offset + limit, len(rows))
            result = {"snapshot_sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                      "total": len(rows), "entries": rows[offset:end],
                      "next_offset": end if end < len(rows) else None}
        elif op == "recall":
            rows = read(root, "memories")["items"]
            if "id" in request:
                result = next(x for x in rows if x["id"] == request["id"])
            else:
                result = {"items": [x for x in rows if request.get("query", "") in x["content"]]}
        else:
            raise ValueError("this adapter is read-only; bind a real backend writer explicitly")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration):
        print("Export adapter could not satisfy the request; prepare fresh complete exports locally.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
