param(
    [ValidateSet("FROM_DUMP", "EMPTY", "from-dump", "empty")]
    [string]$Mode = $(if ($env:TESTBED_INIT_MODE) { $env:TESTBED_INIT_MODE } else { "FROM_DUMP" }),
    [string]$Dump = $(if ($env:TESTBED_DUMP_PATH) { $env:TESTBED_DUMP_PATH } else { "" }),
    [ValidateSet("auto", "plain", "custom")]
    [string]$Format = $(if ($env:TESTBED_DUMP_FORMAT) { $env:TESTBED_DUMP_FORMAT } else { "auto" })
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Test-DockerAvailable
Write-Host "Starting PostgreSQL testbed..."
Invoke-Compose up -d postgres
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
