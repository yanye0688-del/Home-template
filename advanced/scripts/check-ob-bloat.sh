#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
CONFIG=${MEMORYKIT_CONFIG:?Set MEMORYKIT_CONFIG to your private runtime config}
exec python3 "$SCRIPT_DIR/memorykit.py" --config "$CONFIG" bloat "$@"
