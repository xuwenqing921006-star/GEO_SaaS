$ErrorActionPreference = "Stop"

function Invoke-LocalHttpsProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [int]$TimeoutSeconds = 5,
        [switch]$Headers
    )

    $curlArguments = @(
        "--silent",
        "--insecure",
        "--max-time",
        "$TimeoutSeconds"
    )
    if ($Headers) {
        $curlArguments += "--head"
    }
    else {
        $curlArguments += @("--output", "NUL", "--write-out", "%{http_code}")
    }
    $curlArguments += $Uri

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $probeOutput = & curl.exe @curlArguments 2>$null
        $probeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = $probeExitCode
        Output = ($probeOutput -join "`n").Trim()
    }
}

$drillProject = "geo-saas-t013-" + [guid]::NewGuid().ToString("N").Substring(0, 12)
$stackCreated = $false
$drillCompleted = $false
$tempRoot = [IO.Path]::GetTempPath().TrimEnd([IO.Path]::DirectorySeparatorChar)
$tempPath = Join-Path $tempRoot ("geo-saas-t013-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempPath | Out-Null
$resolvedTemp = (Resolve-Path -LiteralPath $tempPath).Path
if (-not $resolvedTemp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "unsafe temporary path"
}

$env:APP_ENV = "production"
$env:APP_VERSION = "0.1.0-rc13"
$env:APP_DOMAIN = "localhost"
$env:WEB_PORT = "55173"
$env:POSTGRES_DB = "geo_saas"
$env:POSTGRES_ADMIN_USER = "postgres"
$env:POSTGRES_ADMIN_PASSWORD = "AdminT013Final2026Safe"
$env:GEO_APP_USER = "geo_app"
$env:GEO_APP_PASSWORD = "RuntimeT013Final2026Safe"
$env:GEO_MIGRATION_USER = "geo_migrator"
$env:GEO_MIGRATION_PASSWORD = "MigrationT013Final2026Safe"
$bytes = New-Object byte[] 32
$randomNumberGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $randomNumberGenerator.GetBytes($bytes)
}
finally {
    $randomNumberGenerator.Dispose()
}
$env:GEO_APP_MASTER_KEY = [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")

try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $keyOutput = docker run --rm `
            -v "${resolvedTemp}:/keys" `
            --entrypoint age-keygen `
            geo-saas/backup:0.1.0-rc13 `
            -o /keys/identity.txt 2>&1
        $keyExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($keyExitCode -ne 0) {
        throw "age key generation failed"
    }
    $recipientLine = $keyOutput |
        Where-Object { "$_" -match "Public key:" } |
        Select-Object -Last 1
    $env:BACKUP_AGE_RECIPIENT = ("$recipientLine" -split "\s+")[-1]

    $stackCreated = $true
    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        up -d db api worker web caddy backup
    if ($LASTEXITCODE -ne 0) {
        throw "production stack startup failed"
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $probe = Invoke-LocalHttpsProbe `
            -Uri "https://localhost/api/v1/health/ready" `
            -TimeoutSeconds 3
        if ($probe.ExitCode -eq 0 -and $probe.Output -eq "200") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        docker compose `
            -p $drillProject `
            -f compose.yaml `
            -f compose.production.yaml `
            ps
        throw "production readiness timeout"
    }

    $metrics = docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T api `
        python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/internal/metrics').read().decode())"
    if ($LASTEXITCODE -ne 0 -or "$metrics" -notmatch "geo_jobs_queue_depth") {
        throw "internal metrics unavailable"
    }

    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T -e BACKUP_FORCE_WEEKLY=1 backup /usr/local/bin/geo-backup
    if ($LASTEXITCODE -ne 0) {
        throw "forced weekly backup failed"
    }

    $weeklyFile = docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T backup sh -c "find /backups/weekly -name '*.tar.age' -type f | head -n 1"
    $weeklyFile = "$weeklyFile".Trim()
    if ($LASTEXITCODE -ne 0 -or -not $weeklyFile) {
        throw "weekly backup missing"
    }
    $weeklyBase = [IO.Path]::GetFileName($weeklyFile)

    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T backup sh -c "mkdir -p /backups/daily-removed && mv /backups/daily/* /backups/daily-removed/ && cd /backups/weekly && sha256sum --check '${weeklyBase}.sha256'"
    if ($LASTEXITCODE -ne 0) {
        throw "weekly checksum failed after daily backup removal"
    }

    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        --profile restore `
        run --rm `
        -v "${resolvedTemp}/identity.txt:/run/secrets/backup_age_identity:ro" `
        -e BACKUP_FILE=$weeklyFile `
        -e CONFIRM_RESTORE=restore-geo_saas `
        restore
    if ($LASTEXITCODE -ne 0) {
        throw "weekly restore failed"
    }

    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T `
        -e PGPASSWORD=$env:GEO_MIGRATION_PASSWORD `
        db psql -U geo_migrator -d geo_saas -v ON_ERROR_STOP=1 `
        -c "INSERT INTO runtime_settings (singleton_key, default_client_monthly_budget_cny_fen, version, updated_at) VALUES (1, 777777, 1, now()) ON CONFLICT (singleton_key) DO UPDATE SET default_client_monthly_budget_cny_fen = 777777, updated_at = now();"
    if ($LASTEXITCODE -ne 0) {
        throw "restore rollback guard setup failed"
    }

    $tamperCommand = @'
set -Eeuo pipefail
work=/work/tampered-restore
mkdir -p "${work}/payload"
age --decrypt --identity /run/secrets/backup_age_identity --output="${work}/archive.tar" "__WEEKLY_FILE__"
tar --extract --file="${work}/archive.tar" --directory="${work}/payload"
printf '{"clients":999999,"facts":999999,"content_versions":999999,"monitoring_samples":999999,"schema":"invalid"}\n' > "${work}/payload/database-counts.json"
(
  cd "${work}/payload"
  sha256sum database.dump files.tar database-counts.json backup-metadata.txt files.sha256 > archive.sha256
)
tar --create --file=- --directory="${work}/payload" . \
  | age --recipient "${BACKUP_AGE_RECIPIENT}" --output=/backups/weekly/tampered.tar.age
(
  cd /backups/weekly
  sha256sum tampered.tar.age > tampered.tar.age.sha256
)
'@.Replace("__WEEKLY_FILE__", $weeklyFile)
    docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        run --rm `
        --entrypoint sh `
        -v "${resolvedTemp}/identity.txt:/run/secrets/backup_age_identity:ro" `
        backup -c $tamperCommand
    if ($LASTEXITCODE -ne 0) {
        throw "tampered backup preparation failed"
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $failedRestoreOutput = docker compose `
            -p $drillProject `
            -f compose.yaml `
            -f compose.production.yaml `
            --profile restore `
            run --rm `
            -v "${resolvedTemp}/identity.txt:/run/secrets/backup_age_identity:ro" `
            -e BACKUP_FILE=/backups/weekly/tampered.tar.age `
            -e CONFIRM_RESTORE=restore-geo_saas `
            restore 2>&1 | ForEach-Object { "$_" }
        $failedRestoreExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $failedRestoreOutput | Write-Output
    if ($failedRestoreExitCode -eq 0) {
        throw "tampered post-validation backup unexpectedly restored"
    }

    $rollbackGuard = docker compose `
        -p $drillProject `
        -f compose.yaml `
        -f compose.production.yaml `
        exec -T `
        -e PGPASSWORD=$env:GEO_MIGRATION_PASSWORD `
        db psql -U geo_migrator -d geo_saas -At `
        -c "SELECT default_client_monthly_budget_cny_fen FROM runtime_settings WHERE singleton_key = 1;"
    if ($LASTEXITCODE -ne 0 -or "$rollbackGuard".Trim() -ne "777777") {
        throw "database was not rolled back after post-restore validation failure"
    }

    $finalReady = Invoke-LocalHttpsProbe `
        -Uri "https://localhost/api/v1/health/ready" `
        -TimeoutSeconds 5
    if ($finalReady.ExitCode -ne 0 -or $finalReady.Output -ne "200") {
        throw "post-restore readiness failed"
    }
    $headers = Invoke-LocalHttpsProbe `
        -Uri "https://localhost/api/v1/health/live" `
        -TimeoutSeconds 5 `
        -Headers
    if (
        $headers.ExitCode -ne 0 `
        -or $headers.Output -notmatch "(?im)^Strict-Transport-Security:\s*.*max-age=31536000"
    ) {
        throw "HSTS missing"
    }

    $drillCompleted = $true
}
finally {
    $cleanupErrors = @()
    if ($stackCreated) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            docker compose `
                -p $drillProject `
                -f compose.yaml `
                -f compose.production.yaml `
                down -v --remove-orphans 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                $cleanupErrors += "Compose stack cleanup failed"
            }
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    if (Test-Path -LiteralPath $resolvedTemp) {
        try {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
        catch {
            $cleanupErrors += "Temporary drill directory cleanup failed"
        }
    }
    if ($cleanupErrors.Count -gt 0) {
        $cleanupMessage = $cleanupErrors -join "; "
        if ($drillCompleted) {
            throw $cleanupMessage
        }
        Write-Warning $cleanupMessage
    }
}

Write-Output "production_drill=passed"
Write-Output "weekly_backup_after_daily_removal=passed"
Write-Output "transactional_restore=passed"
Write-Output "post_validation_database_rollback=passed"
Write-Output "internal_metrics=passed"
Write-Output "https_hsts=passed"
