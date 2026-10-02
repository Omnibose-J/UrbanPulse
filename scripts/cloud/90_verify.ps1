# SOW-MC step 10: one line per check against a deployed (or local production) site. Exit 1 when a line fails.
# ASCII. PowerShell 5.1.
param([Parameter(Mandatory = $true)][string]$Url, [string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
Step ("verify " + $Url) {
    python (Join-Path $PSScriptRoot "verify.py") $Url --env-file $EnvFile
}
