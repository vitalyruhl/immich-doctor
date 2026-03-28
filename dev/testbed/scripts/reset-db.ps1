param(
    [switch]$Force,
    [switch]$RemoveSnapshot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Test-DockerAvailable
Confirm-OrExit -Prompt "Reset the active testbed database volume $(Get-DbVolumeName)? This destroys current DB state." -Force:$Force

Invoke-Compose -CommandArgs @("down", "--remove-orphans")
Remove-VolumeIfExists -Name (Get-DbVolumeName) -Label "Active database volume"
if ($RemoveSnapshot) {
    Confirm-OrExit -Prompt "Also delete snapshot volume $(Get-SnapshotVolumeName)?" -Force:$Force
    Remove-VolumeIfExists -Name (Get-SnapshotVolumeName) -Label "Snapshot volume"
}
Ensure-Volume -Name (Get-DbVolumeName) -Label "Active database volume"
Invoke-Compose -CommandArgs @("up", "-d", "postgres")
Wait-ForPostgres
Write-Host "Reset completed. The database volume is now empty."
