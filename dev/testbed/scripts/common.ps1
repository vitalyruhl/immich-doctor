$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TestbedDir = Split-Path -Parent $ScriptDir
$ComposeFile = Join-Path $TestbedDir "docker-compose.yml"
$EnvFile = Join-Path $TestbedDir ".env"

if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile. Copy .env.example to .env first."
}

function Import-TestbedEnv {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1])
        }
    }
}

Import-TestbedEnv

function Get-ComposeArgs {
    return @("--env-file", $EnvFile, "-f", $ComposeFile)
}

function Invoke-Compose {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )
    & docker compose @(Get-ComposeArgs) @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed."
    }
}

function Get-DbVolumeName {
    if ($env:TESTBED_DB_VOLUME) { return $env:TESTBED_DB_VOLUME }
    return "immich_dev_pgdata"
}

function Get-SnapshotVolumeName {
    if ($env:TESTBED_DB_SNAPSHOT_VOLUME) { return $env:TESTBED_DB_SNAPSHOT_VOLUME }
    return "immich_dev_pgdata_snapshot"
}

function Get-EnvOrDefault {
    param(
        [string]$Name,
        [string]$Default
    )
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function Get-DbServiceName {
    return "postgres"
}

function Get-DbContainerId {
    $id = & docker compose @(Get-ComposeArgs) ps -q (Get-DbServiceName)
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to resolve postgres container id."
    }
    return $id.Trim()
}

function Test-DockerAvailable {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon is not reachable."
    }
}

function Ensure-Volume {
    param([string]$Name)
    & docker volume inspect $Name *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating Docker volume: $Name"
        & docker volume create $Name *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Docker volume $Name."
        }
    }
}

function Confirm-OrExit {
    param(
        [string]$Prompt,
        [switch]$Force
    )
    if ($Force) {
        return
    }
    $reply = Read-Host "$Prompt [y/N]"
    if ($reply -notin @("y", "Y", "yes", "YES")) {
        throw "Aborted."
    }
}

function Wait-ForPostgres {
    param([int]$MaxAttempts = 30)
    $dbName = Get-EnvOrDefault -Name "TESTBED_DB_NAME" -Default "immich"
    $dbUser = Get-EnvOrDefault -Name "TESTBED_DB_USER" -Default "postgres"
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) pg_isready "--dbname=$dbName" "--username=$dbUser" *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL is ready."
            return
        }
        Write-Host "Waiting for PostgreSQL... ($attempt/$MaxAttempts)"
        Start-Sleep -Seconds 2
    }
    throw "PostgreSQL did not become ready in time."
}

function Copy-VolumeContents {
    param(
        [string]$SourceVolume,
        [string]$DestinationVolume
    )
    Ensure-Volume -Name $SourceVolume
    Ensure-Volume -Name $DestinationVolume
    & docker run --rm `
        -v "${SourceVolume}:/from:ro" `
        -v "${DestinationVolume}:/to" `
        alpine:3.20 `
        sh -eu -c "mkdir -p /to && find /to -mindepth 1 -maxdepth 1 -exec rm -rf {} + && cd /from && tar cpf - . | tar xpf - -C /to"
    if ($LASTEXITCODE -ne 0) {
        throw "Volume copy failed."
    }
}

function Restore-DumpIntoDatabase {
    param(
        [string]$DumpPath,
        [string]$DumpFormat
    )
    if (-not (Test-Path $DumpPath)) {
        throw "Dump file not found: $DumpPath"
    }

    $containerId = Get-DbContainerId
    if (-not $containerId) {
        throw "PostgreSQL container is not running."
    }

    $containerDumpPath = "/tmp/immich-testbed.dump"
    $dbUser = Get-EnvOrDefault -Name "TESTBED_DB_USER" -Default "postgres"
    $dbName = Get-EnvOrDefault -Name "TESTBED_DB_NAME" -Default "immich"
    Write-Host "Copying dump into container..."
    & docker cp $DumpPath "${containerId}:${containerDumpPath}"
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed."
    }

    Write-Host "Recreating target database..."
    $recreateCommand = "psql --username='$dbUser' --dbname=postgres -c `"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$dbName' AND pid <> pg_backend_pid();`" >/dev/null; dropdb --if-exists --force --username='$dbUser' '$dbName'; createdb --username='$dbUser' '$dbName'"
    & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) sh -eu -c $recreateCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Database recreate failed."
    }

    if ($DumpFormat -eq "auto") {
        switch -Regex ($DumpPath) {
            "\.(dump|backup|bin)$" { $DumpFormat = "custom"; break }
            "\.sql$" { $DumpFormat = "plain"; break }
            default { throw "Could not infer dump format for $DumpPath. Set TESTBED_DUMP_FORMAT to plain or custom." }
        }
    }

    Write-Host "Restoring database using format: $DumpFormat"
    switch ($DumpFormat) {
        "custom" {
            & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) pg_restore --clean --if-exists --no-owner --no-privileges "--username=$dbUser" "--dbname=$dbName" $containerDumpPath
        }
        "plain" {
            $restoreCommand = "psql --username='$dbUser' --dbname='$dbName' -f '$containerDumpPath'"
            & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) sh -eu -c $restoreCommand
        }
        default {
            throw "Unsupported dump format: $DumpFormat"
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Database restore failed."
    }

    & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) rm -f $containerDumpPath *> $null
    Write-Host "Database restore completed."
}
