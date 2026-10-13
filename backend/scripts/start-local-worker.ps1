$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $backendRoot ".env.runtime"
$runtimeLine = Get-Content -LiteralPath $runtimePath |
    Where-Object { $_ -like "APP_MASTER_KEY=*" } |
    Select-Object -First 1
if (-not $runtimeLine) {
    throw "Runtime master key missing"
}

$containerConfig = (
    docker inspect "geo-saas-t008-pg" | ConvertFrom-Json
)[0].Config.Env
$postgresPassword = (
    $containerConfig |
        Where-Object { $_ -like "POSTGRES_PASSWORD=*" }
) -replace "^POSTGRES_PASSWORD=", ""

$env:APP_MASTER_KEY = $runtimeLine.Substring("APP_MASTER_KEY=".Length)
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "55432"
$env:DB_NAME = "geo_saas_t008"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = $postgresPassword
$env:MODEL_EXECUTION_MODE = "live"
$env:API_READINESS_URL = "http://127.0.0.1:8000/api/v1/health/ready"
$env:STORAGE_ROOT = Join-Path $backendRoot "data"

$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$stdout = Join-Path $backendRoot "worker-live.stdout.log"
$stderr = Join-Path $backendRoot "worker-live.stderr.log"
$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "app.worker") `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Start-Sleep -Seconds 2
if ($process.HasExited) {
    Get-Content -LiteralPath $stderr -Tail 20 -ErrorAction SilentlyContinue
    throw "Local worker failed to start"
}

Write-Output "LOCAL_WORKER_READY=$($process.Id)"
