#!/usr/bin/env bash
# AiDW doctor on Linux/macOS: checks everything (Python, Git, Node, Claude, Codex, login, context,
# MCPs, folders and whether the generated environment is up to date) and ends with READY or NOT READY.
# Changes nothing. To fix what is missing, run ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        exec "$candidate" aidw.py doctor
    fi
done
echo "NOT READY — Python 3.11+ not found. Run ./setup.sh"
exit 1
