param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArgs
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-Compose -CommandArgs $ComposeArgs
