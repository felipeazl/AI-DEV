# Atalho para Windows: .\setup.ps1  (equivale a `python aidev.py setup`)
# Argumentos são repassados, ex.: .\setup.ps1 --reconfigure
$ErrorActionPreference = 'Stop'

$python = $null
foreach ($candidate in 'python', 'py') {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        & $cmd.Source -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $cmd.Source; break }
    }
}

if (-not $python) {
    Write-Host 'Python 3.11+ nao encontrado. Instale com: winget install Python.Python.3.13'
    exit 1
}

& $python (Join-Path $PSScriptRoot 'aidev.py') setup @args
exit $LASTEXITCODE
