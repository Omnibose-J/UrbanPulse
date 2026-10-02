# SOW-MC step 4.2-4.4: copy every public table once from the local database, compare counts, report the size.
# Refuses a target that already holds rows. Run it before any cloud job is scheduled. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("DATABASE_URL")

Step "copy public tables local -> target (one transaction) and compare counts" {
    python (Join-Path $PSScriptRoot "dbtool.py") copy --target-env $EnvFile
}
Write-Output "31_db_copy done"
