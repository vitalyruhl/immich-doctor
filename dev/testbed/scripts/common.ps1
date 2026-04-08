$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TestbedDir = Split-Path -Parent $ScriptDir
$ComposeFile = Join-Path $TestbedDir "docker-compose.yml"
$EnvFile = Join-Path $TestbedDir ".env"
$EnvLocalFile = Join-Path $TestbedDir ".env.local"
$InitialEnvNames = @{}
Get-ChildItem Env: | ForEach-Object {
    $InitialEnvNames[$_.Name] = $true
}

if (-not (Test-Path $EnvFile)) {
    throw "Missing $EnvFile. Copy .env.example to .env first."
}

function Import-TestbedEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return
    }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            $name = $parts[0]
            if ($InitialEnvNames.ContainsKey($name)) {
                return
            }
            [Environment]::SetEnvironmentVariable($name, $parts[1])
        }
    }
}

Import-TestbedEnv -Path $EnvFile
Import-TestbedEnv -Path $EnvLocalFile

function Get-ComposeArgs {
    $args = @("--env-file", $EnvFile)
    if (Test-Path $EnvLocalFile) {
        $args += @("--env-file", $EnvLocalFile)
    }
    $args += @("-f", $ComposeFile)
    return $args
}

function Invoke-Compose {
    param([string[]]$CommandArgs)
    & docker compose @(Get-ComposeArgs) @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed."
    }
}

function Invoke-ComposeExecCapture {
    param([string[]]$CommandArgs)
    $previousNativePreference = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        $output = & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) @CommandArgs 2>&1
        return [pscustomobject]@{
            Output = @($output)
            ExitCode = $LASTEXITCODE
        }
    }
    finally {
        $PSNativeCommandUseErrorActionPreference = $previousNativePreference
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

function Resolve-TestbedSelectedStoragePath {
    $mode = (Get-EnvOrDefault -Name "TESTBED_STORAGE_SOURCE_MODE" -Default "mock").ToLowerInvariant()
    switch ($mode) {
        "mock" {
            $pathValue = Get-EnvOrDefault -Name "TESTBED_MOCK_STORAGE_PATH" -Default "../../data/mock/immich-library"
        }
        "real" {
            $pathValue = Get-EnvOrDefault -Name "TESTBED_REAL_STORAGE_PATH" -Default ""
            if ([string]::IsNullOrWhiteSpace($pathValue)) {
                throw "TESTBED_REAL_STORAGE_PATH is required when TESTBED_STORAGE_SOURCE_MODE=real."
            }
        }
        default {
            throw "Unsupported TESTBED_STORAGE_SOURCE_MODE '$mode'. Use 'mock' or 'real'."
        }
    }

    $resolvedPath = Resolve-HostPath -Path $pathValue
    [Environment]::SetEnvironmentVariable("TESTBED_SELECTED_STORAGE_PATH", $resolvedPath)
    return $resolvedPath
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

function Test-VolumeExists {
    param([string]$Name)
    $volumeNames = & docker volume ls --format "{{.Name}}" --filter "name=$Name" 2> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to list Docker volumes."
    }
    return ($volumeNames | Where-Object { $_ -eq $Name } | Measure-Object).Count -gt 0
}

function Ensure-Volume {
    param(
        [string]$Name,
        [string]$Label = "Docker volume"
    )
    if (Test-VolumeExists -Name $Name) {
        Write-Host "$Label already exists: $Name"
        return
    }
    Write-Host "Creating ${Label}: $Name"
    & docker volume create $Name *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Docker volume $Name."
    }
}

function Require-Volume {
    param(
        [string]$Name,
        [string]$Label = "Docker volume"
    )
    if (-not (Test-VolumeExists -Name $Name)) {
        throw "$Label does not exist: $Name"
    }
    Write-Host "$Label exists: $Name"
}

function Remove-VolumeIfExists {
    param(
        [string]$Name,
        [string]$Label = "Docker volume"
    )
    if (-not (Test-VolumeExists -Name $Name)) {
        Write-Host "$Label already absent: $Name"
        return
    }
    Write-Host "Removing ${Label}: $Name"
    & docker volume rm -f $Name *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove Docker volume $Name."
    }
}

function Resolve-HostPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Host path must not be empty."
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $TestbedDir $Path))
}

Resolve-TestbedSelectedStoragePath *> $null

function Get-DefaultExportPath {
    param(
        [ValidateSet("custom", "plain")]
        [string]$Format = "custom"
    )
    $fileName = if ($Format -eq "plain") { "immich-testbed-export.sql" } else { "immich-testbed-export.dump" }
    return Join-Path $TestbedDir (Join-Path "exports" $fileName)
}

function Resolve-DumpFormat {
    param(
        [string]$DumpPath,
        [string]$DumpFormat
    )
    if ($DumpFormat -eq "auto") {
        switch -Regex ($DumpPath) {
            "\.(dump|backup|bin)$" { return "custom" }
            "\.sql$" { return "plain" }
            default { throw "Could not infer dump format for $DumpPath. Set TESTBED_DUMP_FORMAT to plain or custom." }
        }
    }
    return $DumpFormat
}

function Test-PlainSqlClusterDump {
    param([string]$DumpPath)
    $header = Get-Content -Path $DumpPath -TotalCount 80
    return ($header -match "PostgreSQL database cluster dump")
}

function Ensure-ParentDirectory {
    param([string]$Path)
    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path $parent)) {
        Write-Host "Creating directory: $parent"
        New-Item -ItemType Directory -Path $parent -Force *> $null
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
    & docker run --rm `
        -v "${SourceVolume}:/from:ro" `
        -v "${DestinationVolume}:/to" `
        alpine:3.20 `
        sh -eu -c "mkdir -p /to && find /to -mindepth 1 -maxdepth 1 -exec rm -rf {} + && cd /from && tar cpf - . | tar xpf - -C /to"
    if ($LASTEXITCODE -ne 0) {
        throw "Volume copy failed."
    }
}

function Test-DatabaseExists {
    param([string]$DatabaseName)
    $dbUser = Get-EnvOrDefault -Name "TESTBED_DB_USER" -Default "postgres"
    $query = "SELECT 1 FROM pg_database WHERE datname = '$DatabaseName';"
    $result = Invoke-ComposeExecCapture -CommandArgs @(
        "psql",
        "--username=$dbUser",
        "--dbname=postgres",
        "-Atqc",
        $query
    )
    if ($result.ExitCode -ne 0) {
        throw "Failed to verify database existence for $DatabaseName."
    }
    return (($result.Output -join "`n").Trim() -eq "1")
}

function Restore-DumpIntoDatabase {
    param(
        [string]$DumpPath,
        [string]$DumpFormat
    )
    $resolvedDumpPath = Resolve-HostPath -Path $DumpPath
    if (-not (Test-Path $resolvedDumpPath)) {
        throw "Dump file not found: $resolvedDumpPath"
    }

    $resolvedDumpFormat = Resolve-DumpFormat -DumpPath $resolvedDumpPath -DumpFormat $DumpFormat
    $containerId = Get-DbContainerId
    if (-not $containerId) {
        throw "PostgreSQL container is not running."
    }

    $containerDumpPath = "/tmp/immich-testbed.dump"
    $containerPreparedDumpPath = "/tmp/immich-testbed-prepared.sql"
    $containerRestoreLogPath = "/tmp/immich-testbed-restore.log"
    $dbUser = Get-EnvOrDefault -Name "TESTBED_DB_USER" -Default "postgres"
    $dbName = Get-EnvOrDefault -Name "TESTBED_DB_NAME" -Default "immich"
    $hostPreparedDumpPath = $null

    Write-Host "Copying dump into container..."
    & docker cp $resolvedDumpPath "${containerId}:${containerDumpPath}"
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed."
    }

    $classification = "failure"
    $meaningfulErrorCount = 0
    $structuralErrorCount = 0
    $expectedSkippedStatements = 0

    try {
        switch ($resolvedDumpFormat) {
            "custom" {
                Write-Host "Recreating target database for custom-format restore..."
                $recreateCommand = "psql --username='$dbUser' --dbname=postgres -c `"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$dbName' AND pid <> pg_backend_pid();`" >/dev/null; dropdb --if-exists --force --username='$dbUser' '$dbName'; createdb --username='$dbUser' '$dbName'"
                $recreateResult = Invoke-ComposeExecCapture -CommandArgs @("sh", "-eu", "-c", $recreateCommand)
                if ($recreateResult.ExitCode -ne 0) {
                    throw "Database recreate failed."
                }

                Write-Host "Restoring database using format: custom"
                $restoreCommand = "pg_restore --clean --if-exists --no-owner --no-privileges --username='$dbUser' --dbname='$dbName' '$containerDumpPath' > '$containerRestoreLogPath' 2>&1; status=`$?; grep -E 'ERROR:|FATAL:' '$containerRestoreLogPath' || true; exit `$status"
                $restoreResult = Invoke-ComposeExecCapture -CommandArgs @("sh", "-eu", "-c", $restoreCommand)
                $restoreOutput = @($restoreResult.Output)
                foreach ($line in $restoreOutput) { Write-Host $line }

                $meaningfulErrorCount = @($restoreOutput | Where-Object { $_ -match "(?i)\berror:" }).Count
                $structuralErrorCount = 0

                Wait-ForPostgres
                if ($restoreResult.ExitCode -ne 0 -or -not (Test-DatabaseExists -DatabaseName $dbName)) {
                    $classification = "failure"
                }
                elseif ($meaningfulErrorCount -gt 0) {
                    $classification = "partial success"
                }
                else {
                    $classification = "success"
                }
            }
            "plain" {
                if (Test-PlainSqlClusterDump -DumpPath $resolvedDumpPath) {
                    Write-Host "Detected plain SQL cluster dump. Restoring from maintenance database without pre-creating the target DB."
                    $hostPreparedDumpPath = [System.IO.Path]::GetTempFileName()
                    $reader = [System.IO.File]::OpenText($resolvedDumpPath)
                    $writer = [System.IO.StreamWriter]::new($hostPreparedDumpPath, $false, [System.Text.UTF8Encoding]::new($false))
                    $writer.NewLine = "`n"
                    try {
                        while (($line = $reader.ReadLine()) -ne $null) {
                            if ($line -eq "DROP ROLE IF EXISTS $dbUser;") {
                                $writer.WriteLine("-- immich-doctor skipped bootstrap role drop: $line")
                                $expectedSkippedStatements++
                                continue
                            }
                            if ($line -eq "CREATE ROLE $dbUser;") {
                                $writer.WriteLine("-- immich-doctor skipped bootstrap role create: $line")
                                $expectedSkippedStatements++
                                continue
                            }
                            if ($line.StartsWith("ALTER ROLE $dbUser WITH ")) {
                                $writer.WriteLine("-- immich-doctor skipped bootstrap role alter: $line")
                                $expectedSkippedStatements++
                                continue
                            }
                            $writer.WriteLine($line)
                        }
                    }
                    finally {
                        $reader.Dispose()
                        $writer.Dispose()
                    }

                    & docker cp $hostPreparedDumpPath "${containerId}:${containerPreparedDumpPath}"
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to copy prepared plain SQL dump into container."
                    }
                    if ($expectedSkippedStatements -gt 0) {
                        Write-Host "Skipped bootstrap-role statements for the active testbed login role: $expectedSkippedStatements"
                    }

                    Write-Host "Restoring database using format: plain (cluster-aware mode)"
                    $restoreCommand = "psql --username='$dbUser' --dbname=postgres -v ON_ERROR_STOP=0 -f '$containerPreparedDumpPath' > '$containerRestoreLogPath' 2>&1; status=`$?; grep -E 'ERROR:|FATAL:' '$containerRestoreLogPath' || true; exit `$status"
                }
                else {
                    Write-Host "Detected plain SQL database dump. Recreating target database before restore."
                    $recreateCommand = "psql --username='$dbUser' --dbname=postgres -c `"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$dbName' AND pid <> pg_backend_pid();`" >/dev/null; dropdb --if-exists --force --username='$dbUser' '$dbName'; createdb --username='$dbUser' '$dbName'"
                    $recreateResult = Invoke-ComposeExecCapture -CommandArgs @("sh", "-eu", "-c", $recreateCommand)
                    if ($recreateResult.ExitCode -ne 0) {
                        throw "Database recreate failed."
                    }
                    Write-Host "Restoring database using format: plain (database-only mode)"
                    $restoreCommand = "psql --username='$dbUser' --dbname='$dbName' -v ON_ERROR_STOP=0 -f '$containerDumpPath' > '$containerRestoreLogPath' 2>&1; status=`$?; grep -E 'ERROR:|FATAL:' '$containerRestoreLogPath' || true; exit `$status"
                }

                $restoreResult = Invoke-ComposeExecCapture -CommandArgs @("sh", "-eu", "-c", $restoreCommand)
                $restoreOutput = @($restoreResult.Output)
                foreach ($line in $restoreOutput) { Write-Host $line }

                $meaningfulErrorCount = @($restoreOutput | Where-Object { $_ -match "(?i)\berror:" }).Count
                $structuralPatterns = @(
                    "cannot drop the currently open database",
                    "current user cannot be dropped",
                    "role `"$dbUser`" already exists",
                    "database `"$dbName`" already exists"
                )
                $structuralErrorCount = @(
                    foreach ($pattern in $structuralPatterns) {
                        $restoreOutput | Where-Object { $_ -match [regex]::Escape($pattern) }
                    }
                ).Count

                Wait-ForPostgres
                if ($restoreResult.ExitCode -ne 0 -or $structuralErrorCount -gt 0 -or -not (Test-DatabaseExists -DatabaseName $dbName)) {
                    $classification = "failure"
                }
                elseif ($meaningfulErrorCount -gt 0) {
                    $classification = "partial success"
                }
                else {
                    $classification = "success"
                }
            }
            default {
                throw "Unsupported dump format: $resolvedDumpFormat"
            }
        }

        Write-Host "Restore classification: $classification"
        if ($expectedSkippedStatements -gt 0) {
            Write-Host "Expected skipped statements: $expectedSkippedStatements"
        }
        if ($structuralErrorCount -gt 0) {
            Write-Host "Structural restore errors: $structuralErrorCount"
        }
        if ($meaningfulErrorCount -gt 0) {
            Write-Host "Meaningful restore errors: $meaningfulErrorCount"
        }

        if ($classification -eq "failure") {
            throw "Restore classification: failure"
        }

        return [pscustomobject]@{
            Classification = $classification
            DumpFormat = $resolvedDumpFormat
            ExpectedSkippedStatements = $expectedSkippedStatements
            StructuralErrorCount = $structuralErrorCount
            MeaningfulErrorCount = $meaningfulErrorCount
        }
    }
    finally {
        if ($hostPreparedDumpPath -and (Test-Path $hostPreparedDumpPath)) {
            Remove-Item -LiteralPath $hostPreparedDumpPath -Force
        }
        Invoke-ComposeExecCapture -CommandArgs @("rm", "-f", $containerDumpPath, $containerPreparedDumpPath, $containerRestoreLogPath) *> $null
    }
}
