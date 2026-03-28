param(
    [string]$Output = $(if ($env:TESTBED_EXPORT_PATH) { $env:TESTBED_EXPORT_PATH } else { "" }),
    [ValidateSet("custom", "plain")]
    [string]$Format = "custom"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

if (-not $Output) {
    throw "TESTBED_EXPORT_PATH or -Output is required."
}

Test-DockerAvailable
Invoke-Compose up -d postgres
Wait-ForPostgres

$containerId = Get-DbContainerId
$containerDumpPath = "/tmp/immich-export.dump"
$dbUser = if ($env:TESTBED_DB_USER) { $env:TESTBED_DB_USER } else { "postgres" }
$dbName = if ($env:TESTBED_DB_NAME) { $env:TESTBED_DB_NAME } else { "immich" }

switch ($Format) {
    "custom" {
        & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) pg_dump --clean --if-exists --format=custom "--username=$dbUser" "--dbname=$dbName" "--file=$containerDumpPath"
    }
    "plain" {
        & docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) sh -eu -c "pg_dump --clean --if-exists --username='$dbUser' --dbname='$dbName' > '$containerDumpPath'"
    }
}
if ($LASTEXITCODE -ne 0) {
    throw "Database export failed."
}

& docker cp "${containerId}:${containerDumpPath}" $Output
if ($LASTEXITCODE -ne 0) {
    throw "Failed to copy export to host path."
}

& docker compose @(Get-ComposeArgs) exec -T (Get-DbServiceName) rm -f $containerDumpPath *> $null
Write-Host "Export completed: $Output"
