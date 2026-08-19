#!/bin/bash
# Backs up Claude auto-memory into the repo for version control
# Derive the project-memory directory from this checkout's own path rather than
# hardcoding one machine's, so the script works on any collaborator's fork.
# Claude Code slugifies the absolute path: C:\Users\me\labscript-suite
# becomes c--Users-me-labscript-suite.
ROOT="$(git rev-parse --show-toplevel)"
SLUG="$(cd "$ROOT" && pwd -W 2>/dev/null || echo "$ROOT")"
SLUG="$(echo "$SLUG" | sed -e 's#[:/\\]#-#g')"
SRC="$HOME/.claude/projects/$SLUG/memory"
DST="$ROOT/.claude/memory-backup"

if [ ! -d "$SRC" ]; then
    echo "No project memory directory found at: $SRC" >&2
    echo "(Claude Code creates it per checkout path; nothing to back up.)" >&2
    exit 0
fi
mkdir -p "$DST"
cp -v "$SRC"/* "$DST"/
echo "Memory backed up to $DST at $(date)"
