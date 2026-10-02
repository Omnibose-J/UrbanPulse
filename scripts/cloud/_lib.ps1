# Shared helpers for scripts/cloud. ASCII. PowerShell 5.1.
# Rule: a value read from an env file is never written to the console, a log or a command line that is echoed.
# Dot-source after setting $Plan:  . (Join-Path $PSScriptRoot "_lib.ps1")

$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Region = "asia-northeast3"

# One table for the cloud deploy and the local rehearsal, so both run the same args and limits.
$EngineJobs = @(
    @{ Name = "urbanpulse-healthcheck";   JobArgs = "healthcheck";   Cpu = "1"; Memory = "512Mi"; Timeout = "5m" },
    @{ Name = "urbanpulse-collect";       JobArgs = "collect";       Cpu = "1"; Memory = "1Gi";   Timeout = "10m" },
    @{ Name = "urbanpulse-forecast";      JobArgs = "forecast";      Cpu = "2"; Memory = "4Gi";   Timeout = "30m" },
    @{ Name = "urbanpulse-evaluate";      JobArgs = "evaluate";      Cpu = "1"; Memory = "1Gi";   Timeout = "20m" },
    @{ Name = "urbanpulse-sync-holidays"; JobArgs = "sync_holidays"; Cpu = "1"; Memory = "512Mi"; Timeout = "10m" },
    @{ Name = "urbanpulse-ingest-raw";    JobArgs = "ingest_raw";    Cpu = "1"; Memory = "1Gi";   Timeout = "20m" }
)
$EngineSecrets = @(
    @{ Secret = "urbanpulse-database-url";  Name = "DATABASE_URL" },
    @{ Secret = "urbanpulse-seoul-api-key"; Name = "SEOUL_API_KEY" },
    @{ Secret = "urbanpulse-kasi-api-key";  Name = "KASI_API_KEY" }
)

function Read-EnvFile([string]$Path) {
    $full = $Path
    if (-not [System.IO.Path]::IsPathRooted($full)) { $full = Join-Path $Repo $Path }
    if (-not (Test-Path -LiteralPath $full)) {
        Write-Output ("missing env file: " + $Path)
        exit 1
    }
    $values = @{}
    foreach ($raw in [System.IO.File]::ReadAllLines($full, [System.Text.Encoding]::UTF8)) {
        $line = $raw.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { continue }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { continue }
        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($value.Length -gt 0) { $values[$line.Substring(0, $eq).Trim()] = $value }
    }
    return $values
}

function Assert-Names($Values, [string[]]$Names) {
    $lack = @()
    foreach ($name in $Names) { if (-not $Values.ContainsKey($name)) { $lack += $name } }
    if ($lack.Count -gt 0) {
        Write-Output ("missing in env file: " + ($lack -join " "))
        exit 1
    }
}

# Run one action. In plan mode only the label is printed. A non-zero exit of a native tool stops the script.
function Step([string]$Label, [scriptblock]$Action) {
    if ($Plan) { Write-Output ("plan  " + $Label); return }
    Write-Output ("run   " + $Label)
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Output ("FAIL  " + $Label + " (exit " + $LASTEXITCODE + ")")
        exit 1
    }
}

# Create only when the test finds nothing. Prints `exists` or `created`.
function Ensure([string]$Label, [scriptblock]$Test, [scriptblock]$Create) {
    if ($Plan) { Write-Output ("plan  ensure " + $Label); return }
    $global:LASTEXITCODE = 0
    & $Test 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Output ("exists  " + $Label); return }
    $global:LASTEXITCODE = 0
    & $Create
    if ($LASTEXITCODE -ne 0) {
        Write-Output ("FAIL  create " + $Label + " (exit " + $LASTEXITCODE + ")")
        exit 1
    }
    Write-Output ("created " + $Label)
}

# A value goes to a tool through a file the tool reads; the file lives for one call.
function With-SecretFile([string]$Value, [scriptblock]$Action) {
    $file = Join-Path $env:TEMP ("up-" + [System.Guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($file, $Value, (New-Object System.Text.UTF8Encoding($false)))
        & $Action $file
    } finally {
        Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
    }
}

function Bucket-Name($Values) { return ($Values["GCP_PROJECT"] + "-urbanpulse-raw") }
function Engine-Account($Values) { return ("urbanpulse-engine@" + $Values["GCP_PROJECT"] + ".iam.gserviceaccount.com") }
function Scheduler-Account($Values) { return ("urbanpulse-scheduler@" + $Values["GCP_PROJECT"] + ".iam.gserviceaccount.com") }
