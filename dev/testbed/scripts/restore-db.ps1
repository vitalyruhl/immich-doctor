param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

Test-DockerAvailable
Confirm-OrExit -Prompt "Restore $(Get-DbVolumeName) from snapshot $(Get-SnapshotVolumeName)? This overwrites the active database volume." -Force:$Force

Invoke-Compose down --remove-orphans
Copy-VolumeContents -SourceVolume (Get-SnapshotVolumeName) -DestinationVolume (Get-DbVolumeName)
Invoke-Compose up -d postgres
Wait-ForPostgres
Write-Host "Restore completed from $(Get-SnapshotVolumeName)."
