# Failure alerts: an e-mail channel and one Cloud Monitoring policy that fires when a Cloud Run job execution fails.
# The address is the project owner's (read from gcloud), never typed here. Idempotent. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT")
$P = $v["GCP_PROJECT"]
$email = (& gcloud config get-value account 2>$null | Out-String).Trim()
if ($email.Length -eq 0) { Write-Output "FAIL  no gcloud account"; exit 1 }

Step "enable the monitoring API" { gcloud services enable monitoring.googleapis.com --project $P }
$args = @((Join-Path $PSScriptRoot "alerts.py"), "--project", $P, "--email", $email)
if ($Plan) { $args += "--plan" }
& python @args
if ($LASTEXITCODE -ne 0) { Write-Output "FAIL  alerts"; exit 1 }
Write-Output "65_alerts done"
