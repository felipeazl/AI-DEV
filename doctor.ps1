# AiDW doctor on Windows: checks everything (Python, Git, Node, Claude, Codex, login, context,
# MCPs, folders and whether the generated environment is up to date) and ends with READY or NOT READY.
# Changes nothing. To fix what is missing, run .\setup.ps1
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
    Write-Host 'NOT READY - Python 3.11+ not found. Run .\setup.ps1 (it offers to install it).'
    exit 1
}

& $python (Join-Path $PSScriptRoot 'aidw.py') doctor
exit $LASTEXITCODE
