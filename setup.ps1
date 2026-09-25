# Setup do AiDW no Windows: garante o Python 3.11+ e chama `python aidw.py setup`, que cuida do
# resto (Git, Node, CLI do provedor, wizard, geração do ambiente, MCPs e doctor).
# Argumentos são repassados, ex.: .\setup.ps1 --reconfigure
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
    Write-Host 'Python 3.11+ nao encontrado.'
    $answer = Read-Host 'Instalar agora com winget (Python.Python.3.13)? (s/n) [s]'
    if ($answer -eq '' -or $answer -match '^(s|sim|y|yes)$') {
        winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
        # O PATH novo so vale em terminais novos; recarrega para esta sessao.
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        $python = Find-Python
    }
    if (-not $python) {
        Write-Host 'Instale o Python 3.11+ (winget install Python.Python.3.13), reabra o terminal e rode de novo.'
        exit 1
    }
}

& $python (Join-Path $PSScriptRoot 'aidw.py') setup @args
exit $LASTEXITCODE
