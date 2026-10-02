# API with auto-reload + Vite dev server on http://localhost:5173 (proxies /api to :8787)
# Run with:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
# Ctrl+C (or closing either server) stops both process trees.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$origin = Get-Location
$api = $null
$ui = $null

function Stop-Tree($proc) {
    # Never throws: a child that already exited (or a taskkill "not found") must not skip the other cleanup.
    if ($null -eq $proc) { return }
    try {
        if (-not $proc.HasExited) {
            $ErrorActionPreference = "Continue"
            & taskkill /PID $proc.Id /T /F 2>&1 | Out-Null
        }
    } catch {
        Write-Warning "could not stop process $($proc.Id): $_"
    }
}

try {
    Set-Location $root
    if (-not $env:LEDGER_DATA_DIR) { $env:LEDGER_DATA_DIR = Join-Path $root "data" }
    if (-not (Test-Path $env:LEDGER_DATA_DIR)) {
        New-Item -ItemType Directory -Path $env:LEDGER_DATA_DIR | Out-Null
        Set-Content -Path (Join-Path $env:LEDGER_DATA_DIR ".gitignore") -Value "*" -Encoding ascii
    }
    $api = Start-Process -FilePath "$root\.venv\Scripts\python.exe" -WorkingDirectory $root -PassThru -NoNewWindow `
        -ArgumentList @("-m", "uvicorn", "ledger_agent.api.main:build_app_from_env", "--factory", "--reload", "--port", "8787")
    $ui = Start-Process -FilePath "npm.cmd" -WorkingDirectory (Join-Path $root "frontend") -PassThru -NoNewWindow `
        -ArgumentList @("run", "dev")
    Write-Host "API pid $($api.Id) on :8787, Vite pid $($ui.Id) on :5173. Press Ctrl+C to stop both."
    while (-not $api.HasExited -and -not $ui.HasExited) { Start-Sleep -Milliseconds 500 }
} finally {
    try {
        Stop-Tree $api
    } finally {
        try {
            Stop-Tree $ui
        } finally {
            Set-Location $origin
        }
    }
}
