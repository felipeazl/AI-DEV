#!/usr/bin/env bash
# AiDW setup on Linux/macOS: makes sure Python 3.11+ is present and calls `python3 aidw.py setup`, which takes
# care of the rest (Git, Node, Claude and Codex, folders, wizard, environment generation, MCPs and doctor).
# Arguments are passed through, e.g.: ./setup.sh --reconfigure
set -euo pipefail

cd "$(dirname "$0")"

find_python() {
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
            echo "$candidate"
            return
        fi
    done
}

python="$(find_python)"
if [ -z "$python" ]; then
    echo "Python 3.11+ not found."
    echo "  macOS:         brew install python"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Fedora:        sudo dnf install python3"
    exit 1
fi

exec "$python" aidw.py setup "$@"
