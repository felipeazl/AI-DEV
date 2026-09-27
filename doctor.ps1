# Doctor do AiDW no Windows: verifica tudo (Python, Git, Node, Claude, Codex, login, contexto,
# MCPs, pastas e se o ambiente gerado está em dia) e termina com PRONTO ou NÃO PRONTO.
# Não altera nada. Para corrigir o que faltar, rode .\setup.ps1
$ErrorActionPreference = 'Stop'

function Find-Python {
    foreach ($candidate in 'python', 'py') {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            & $cmd.Source -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host 'NAO PRONTO - Python 3.11+ nao encontrado. Rode .\setup.ps1 (ele oferece instalar).'
    exit 1
}

& $python (Join-Path $PSScriptRoot 'aidw.py') doctor
exit $LASTEXITCODE
