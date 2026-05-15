#!/bin/bash
# Backs up Claude auto-memory into the repo for version control
SRC="$HOME/.claude/projects/c--Users-radmo-labscript-suite/memory"
DST="$(git rev-parse --show-toplevel)/.claude/memory-backup"
mkdir -p "$DST"
cp -v "$SRC"/* "$DST"/
echo "Memory backed up to $DST at $(date)"
