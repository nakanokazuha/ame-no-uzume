#!/bin/sh
set -eu

SOURCE_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_DIRECTORY="$HOME/.hermes/agent-hooks"
TARGET_EMITTER="$TARGET_DIRECTORY/yume-observer.py"

install -d -m 0700 "$TARGET_DIRECTORY"
install -m 0700 "$SOURCE_DIRECTORY/emit.py" "$TARGET_EMITTER"

cat "$SOURCE_DIRECTORY/config.example.yaml"
