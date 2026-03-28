param(
    [string]$Mode,
    [string]$Dump,
    [string]$Format
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$Mode = if ($PSBoundParameters.ContainsKey("Mode")) { $Mode } else { Get-EnvOrDefault -Name "TESTBED_INIT_MODE" -Default "FROM_DUMP" }
$Dump = if ($PSBoundParameters.ContainsKey("Dump")) { $Dump } else { Get-EnvOrDefault -Name "TESTBED_DUMP_PATH" -Default "" }
$Format = if ($PSBoundParameters.ContainsKey("Format")) { $Format } else { Get-EnvOrDefault -Name "TESTBED_DUMP_FORMAT" -Default "auto" }

$validModes = @("FROM_DUMP", "EMPTY", "from-dump", "empty")
if ($Mode -notin $validModes) {
    throw "Unsupported mode: $Mode"
}

$validFormats = @("auto", "plain", "custom")
if ($Format -notin $validFormats) {
    throw "Unsupported dump format option: $Format"
}

Test-DockerAvailable
Write-Host "Starting PostgreSQL testbed..."
Invoke-Compose -CommandArgs @("up", "-d", "postgres")
Wait-ForPostgres

switch ($Mode.ToUpperInvariant()) {
    "FROM_DUMP" {
        if (-not $Dump) {
            throw "TESTBED_DUMP_PATH or -Dump is required for FROM_DUMP mode."
        }
        Restore-DumpIntoDatabase -DumpPath $Dump -DumpFormat $Format
    }
    "EMPTY" {
        Write-Host "Leaving database empty as requested."
    }
    default {
        throw "Unsupported mode: $Mode"
    }
}

Write-Host "Testbed initialization complete."
