$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python fetch_macro.py --local
if ($LASTEXITCODE -ne 0) {
    throw "Local market data refresh failed with exit code $LASTEXITCODE."
}
