# AccessWalk one-shot setup for Windows (PowerShell).
# Run from the repo root:   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$EnvName = "accesswalk"

function Find-Micromamba {
    # The micromamba shell hook defines a PowerShell *function* named micromamba and sets
    # MAMBA_EXE to the real binary. Prefer that, then a real executable on PATH.
    if ($env:MAMBA_EXE -and (Test-Path $env:MAMBA_EXE)) { return $env:MAMBA_EXE }
    $cmd = Get-Command micromamba -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:LOCALAPPDATA\micromamba\micromamba.exe",
        "$env:USERPROFILE\micromamba\micromamba.exe",
        "$env:USERPROFILE\AppData\Local\micromamba\micromamba.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

$mm = Find-Micromamba
if (-not $mm) {
    Write-Host "micromamba not found - installing (official installer)..." -ForegroundColor Yellow
    Invoke-Expression ((Invoke-WebRequest -Uri https://micro.mamba.pm/install.ps1 -UseBasicParsing).Content)
    $mm = Find-Micromamba
    if (-not $mm) { throw "micromamba installed but not found. Open a new PowerShell window and re-run setup.ps1." }
}
if ((Split-Path $mm -Leaf) -notmatch '^micromamba(\.exe)?$') { throw "Expected micromamba.exe but found '$mm'. Set MAMBA_EXE to your micromamba.exe path." }
Write-Host "Using micromamba: $mm" -ForegroundColor Cyan
& $mm --version

$existing = & $mm env list | Select-String -Pattern "^\s*$EnvName\s"
if ($existing) {
    Write-Host "Env '$EnvName' exists - updating from environment.yml" -ForegroundColor Cyan
    & $mm update -y -n $EnvName -f environment.yml
} else {
    Write-Host "Creating env '$EnvName' from environment.yml" -ForegroundColor Cyan
    & $mm create -y -n $EnvName -f environment.yml
}
if ($LASTEXITCODE -ne 0) { throw "micromamba failed (exit $LASTEXITCODE)" }

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example - open it and paste your keys." -ForegroundColor Yellow
}

Write-Host "`nVersions inside the env:" -ForegroundColor Cyan
& $mm run -n $EnvName python --version
& $mm run -n $EnvName node --version
& $mm run -n $EnvName ffmpeg -hide_banner -version | Select-Object -First 1

Write-Host "`nDone. Next:" -ForegroundColor Green
Write-Host "  1. notepad .env            (paste MODEL_API_KEY and BASETEN_API_KEY)"
Write-Host "  2. micromamba run -n $EnvName python scripts\check_setup.py"
