# Build the frontend if needed and serve UI + API on http://localhost:8787
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $env:LEDGER_DATA_DIR) { $env:LEDGER_DATA_DIR = Join-Path $root "data" }
if (-not (Test-Path $env:LEDGER_DATA_DIR)) {
    New-Item -ItemType Directory -Path $env:LEDGER_DATA_DIR | Out-Null
    Set-Content -Path (Join-Path $env:LEDGER_DATA_DIR ".gitignore") -Value "*" -Encoding ascii
}
if (-not (Test-Path "frontend\dist")) {
    Push-Location frontend
    npm ci
    npm run build
    Pop-Location
}
& "$root\.venv\Scripts\python.exe" -m uvicorn ledger_agent.api.main:build_app_from_env --factory --port 8787
