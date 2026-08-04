#!/bin/sh
set -eu

SOURCE_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TARGET_DIRECTORY="$HOME/.hermes/agent-hooks"
TARGET_EMITTER="$TARGET_DIRECTORY/yume-observer.py"

install -d -m 0700 "$TARGET_DIRECTORY"
install -m 0700 "$SOURCE_DIRECTORY/emit.py" "$TARGET_EMITTER"

printf '%s\n' "Merge the following entries into your existing top-level hooks mapping."
printf '%s\n' "Do not paste a second hooks: key or replace unrelated hook entries."
cat "$SOURCE_DIRECTORY/config.example.yaml"
