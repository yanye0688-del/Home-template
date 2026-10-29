#!/usr/bin/env python3
import os,sys
from memorykit import main
if __name__ == "__main__":
    config=os.environ.get("MEMORYKIT_CONFIG")
    if not config:raise SystemExit("Set MEMORYKIT_CONFIG to a private runtime config")
    raise SystemExit(main(["--config",config,"handoff",*sys.argv[1:]]))
