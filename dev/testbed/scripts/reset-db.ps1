param(
    [switch]$Force,
    [switch]$RemoveSnapshot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Test-DockerAvailable
Confirm-OrExit -Prompt "Reset the active testbed database volume $(Get-DbVolumeName)? This destroys current DB state." -Force:$Force

Invoke-Compose down --remove-orphans
& docker volume rm -f (Get-DbVolumeName) *> $null
if ($RemoveSnapshot) {
    Confirm-OrExit -Prompt "Also delete snapshot volume $(Get-SnapshotVolumeName)?" -Force:$Force
    & docker volume rm -f (Get-SnapshotVolumeName) *> $null
}
Ensure-Volume -Name (Get-DbVolumeName)
Invoke-Compose up -d postgres
Wait-ForPostgres
Write-Host "Reset completed. The database volume is now empty."
