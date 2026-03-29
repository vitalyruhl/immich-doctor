param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Test-DockerAvailable
Confirm-OrExit -Prompt "Overwrite snapshot volume $(Get-SnapshotVolumeName) from $(Get-DbVolumeName)?" -Force:$Force

Require-Volume -Name (Get-DbVolumeName) -Label "Active database volume"
Ensure-Volume -Name (Get-SnapshotVolumeName) -Label "Snapshot volume"
Write-Host "Stopping PostgreSQL for a consistent volume snapshot..."
Invoke-Compose -CommandArgs @("stop", (Get-DbServiceName))
Copy-VolumeContents -SourceVolume (Get-DbVolumeName) -DestinationVolume (Get-SnapshotVolumeName)
Invoke-Compose -CommandArgs @("start", (Get-DbServiceName))
Wait-ForPostgres
Write-Host "Snapshot completed: $(Get-SnapshotVolumeName)"
