#!/usr/bin/env bash
# Minimal Terminal FLAC Player Launcher
# CachyOS & PipeWire Bit-Perfect Audio Engine

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$1" ]; then
    python3 main.py "$1"
else
    python3 main.py
fi
