$ErrorActionPreference = "Stop"

if (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue) {
    throw "Port 8000 is occupied"
}

$backendRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $backendRoot ".env.runtime"
$runtimeLine = Get-Content -LiteralPath $runtimePath |
    Where-Object { $_ -like "APP_MASTER_KEY=*" } |
    Select-Object -First 1
if (-not $runtimeLine) {
    throw "Runtime master key missing"
}

$container = "geo-saas-t008-pg"
$containerConfig = (docker inspect $container | ConvertFrom-Json)[0].Config.Env
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
$env:STORAGE_ROOT = Join-Path $backendRoot "data"

$stdout = Join-Path $backendRoot "api-live.stdout.log"
$stderr = Join-Path $backendRoot "api-live.stderr.log"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 300
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
} until ($listener -or (Get-Date) -gt $deadline -or $process.HasExited)

if (-not $listener) {
    Get-Content -LiteralPath $stderr -Tail 20 -ErrorAction SilentlyContinue
    throw "Live API failed to start"
}

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/health/ready" | Out-Null
Write-Output "LIVE_API_READY=$($listener.OwningProcess)"
