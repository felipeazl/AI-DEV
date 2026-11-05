# AiDW setup on Windows: makes sure Python 3.11+ is present and calls `python aidw.py setup`, which takes care
# of the rest (Git, Node, Claude and Codex, folders, wizard, environment generation, MCPs and doctor).
# Arguments are passed through, e.g.: .\setup.ps1 --reconfigure
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
    Write-Host 'Python 3.11+ not found.'
    $answer = Read-Host 'Install it now with winget (Python.Python.3.13)? (y/n) [y]'
    if ($answer -eq '' -or $answer -match '^(s|sim|y|yes)$') {
        winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
        # The new PATH only applies to new terminals; reload it for this session.
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        $python = Find-Python
    }
    if (-not $python) {
        Write-Host 'Install Python 3.11+ (winget install Python.Python.3.13), reopen the terminal and run this again.'
        exit 1
    }
}

& $python (Join-Path $PSScriptRoot 'aidw.py') setup @args
exit $LASTEXITCODE
