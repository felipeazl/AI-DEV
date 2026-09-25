#!/usr/bin/env bash
# Setup do AiDW no Linux/macOS: garante o Python 3.11+ e chama `python3 aidw.py setup`, que cuida
# do resto (Git, Node, CLI do provedor, wizard, geração do ambiente, MCPs e doctor).
# Argumentos são repassados, ex.: ./setup.sh --reconfigure
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
    echo "Python 3.11+ não encontrado."
    echo "  macOS:         brew install python"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Fedora:        sudo dnf install python3"
    exit 1
fi

exec "$python" aidw.py setup "$@"
