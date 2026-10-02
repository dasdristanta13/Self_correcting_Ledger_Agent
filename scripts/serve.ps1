# Build the frontend if needed and serve UI + API on http://localhost:8787
# Run with:  powershell -ExecutionPolicy Bypass -File scripts\serve.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$origin = Get-Location
try {
    Set-Location $root
    if (-not $env:LEDGER_DATA_DIR) { $env:LEDGER_DATA_DIR = Join-Path $root "data" }
    if (-not (Test-Path $env:LEDGER_DATA_DIR)) {
        New-Item -ItemType Directory -Path $env:LEDGER_DATA_DIR | Out-Null
        Set-Content -Path (Join-Path $env:LEDGER_DATA_DIR ".gitignore") -Value "*" -Encoding ascii
    }
    if (-not (Test-Path "frontend\dist")) {
        Push-Location frontend
        try {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed (exit code $LASTEXITCODE). Fix the error above and re-run." }
            npm run build
            if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit code $LASTEXITCODE). Fix the error above and re-run." }
        } finally {
            Pop-Location
        }
    }
    & "$root\.venv\Scripts\python.exe" -m uvicorn ledger_agent.api.main:build_app_from_env --factory --port 8787
} finally {
    Set-Location $origin
}
