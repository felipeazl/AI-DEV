#!/usr/bin/env bash
# Atalho para Linux/macOS: ./setup.sh  (equivale a `python3 aidev.py setup`)
# Argumentos são repassados, ex.: ./setup.sh --reconfigure
set -euo pipefail

cd "$(dirname "$0")"

python=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        python="$candidate"
        break
    fi
done

if [ -z "$python" ]; then
    echo "Python 3.11+ não encontrado."
    echo "  macOS:         brew install python"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Fedora:        sudo dnf install python3"
    exit 1
fi

exec "$python" aidev.py setup "$@"
