# API with auto-reload (background job) + Vite dev server on http://localhost:5173
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $env:LEDGER_DATA_DIR) { $env:LEDGER_DATA_DIR = Join-Path $root "data" }
if (-not (Test-Path $env:LEDGER_DATA_DIR)) {
    New-Item -ItemType Directory -Path $env:LEDGER_DATA_DIR | Out-Null
    Set-Content -Path (Join-Path $env:LEDGER_DATA_DIR ".gitignore") -Value "*" -Encoding ascii
}
$py = "$root\.venv\Scripts\python.exe"
$data = $env:LEDGER_DATA_DIR
$api = Start-Job -ScriptBlock {
    param($py, $root, $data)
    Set-Location $root
    $env:LEDGER_DATA_DIR = $data
    & $py -m uvicorn ledger_agent.api.main:build_app_from_env --factory --reload --port 8787
} -ArgumentList $py, $root, $data
try {
    Push-Location frontend
    npm run dev
} finally {
    Pop-Location
    Stop-Job $api
    Remove-Job $api
}
