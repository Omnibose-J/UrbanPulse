# Print which cloud inputs are present. Names only. Never a value.
# ASCII. PowerShell 5.1. Idempotent: reads tools and .env.cloud, changes nothing.
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $Repo

function Write-Item([string]$Name, [string]$State) {
    Write-Output ($Name + " " + $State)
}

$u1 = "missing"
$gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
if ($null -ne $gcloud) {
    $project = & gcloud config get-value project 2>$null
    $projectText = ""
    if ($null -ne $project) { $projectText = ($project | Out-String).Trim() }
    $hasProject = $projectText.Length -gt 0 -and $projectText -ne "(unset)"
    $billing = ""
    if ($hasProject) {
        $billing = (& gcloud billing projects describe $projectText --format="value(billingEnabled)" 2>$null | Out-String).Trim()
    }
    if ($hasProject -and $billing -eq "True") { $u1 = "present" }
}
Write-Item "U1" $u1

$u2 = "missing"
$supabase = Get-Command supabase -ErrorAction SilentlyContinue
if ($null -ne $supabase) {
    $listing = & supabase projects list 2>$null | Out-String
    if ($LASTEXITCODE -eq 0 -and $listing -match "Seoul") { $u2 = "present" }
}
Write-Item "U2" $u2

$required = @(
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_PROJECT_REF",
    "GCP_PROJECT",
    "SEOUL_API_KEY",
    "KASI_API_KEY",
    "ADMIN_TOKEN"
)
$set = @{}
$cloudFile = Join-Path $Repo ".env.cloud"
if (Test-Path -LiteralPath $cloudFile) {
    Get-Content -LiteralPath $cloudFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -gt 0) { $set[$name] = $true }
    }
}
$have = @()
$lack = @()
foreach ($name in $required) {
    if ($set.ContainsKey($name)) { $have += $name } else { $lack += $name }
}
if ($lack.Count -eq 0 -and $have.Count -eq $required.Count) {
    Write-Item "U3" "present"
} else {
    Write-Output ("U3 missing " + ($lack -join " "))
}
Write-Output ("U3 names " + ($have -join " "))

$u4 = "missing"
$vercel = Get-Command vercel -ErrorAction SilentlyContinue
if ($null -ne $vercel) {
    & vercel whoami 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) { $u4 = "present" }
}
Write-Item "U4" $u4

if ($u1 -eq "present" -and $u2 -eq "present" -and $lack.Count -eq 0 -and $u4 -eq "present") { exit 0 }
exit 1
