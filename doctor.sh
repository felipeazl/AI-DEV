#!/usr/bin/env bash
# Doctor do AiDW no Linux/macOS: verifica tudo (Python, Git, Node, Claude, Codex, login, contexto,
# MCPs, pastas e se o ambiente gerado está em dia) e termina com PRONTO ou NÃO PRONTO.
# Não altera nada. Para corrigir o que faltar, rode ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        exec "$candidate" aidw.py doctor
    fi
done
echo "NÃO PRONTO — Python 3.11+ não encontrado. Rode ./setup.sh"
exit 1
