# SOW-MC step 8: close the gap between the data copy and now, then stop the laptop's jobs.
# -Since is the KST date of the data copy (31_db_copy). Nothing is deleted; the local tasks are disabled, not removed.
# ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [Parameter(Mandatory = $true)][string]$Since, [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT", "DATABASE_URL")
$P = $v["GCP_PROJECT"]
$tool = Join-Path $PSScriptRoot "dbtool.py"
$first = [datetime]::ParseExact($Since, "yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)

Step "the two newest cloud collects ended ok" {
    python $tool last-runs --target-env $EnvFile --job collect --count 2
}
Step "local forecast once more, so both sides are built on the same day for the comparison" {
    python -m engine forecast
}
foreach ($task in @("UrbanPulse collect", "UrbanPulse forecast", "UrbanPulse evaluate")) {
    Step ("disable local task " + $task) { Disable-ScheduledTask -TaskName $task | Out-Null }
}
Step "upload the raw folders written since the first upload" {
    & (Join-Path $PSScriptRoot "40_raw_upload.ps1") -EnvFile $EnvFile
}
$today = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([datetime]::UtcNow, "Korea Standard Time").Date
for ($day = $first; $day -le $today; $day = $day.AddDays(1)) {
    $date = $day.ToString("yyyy-MM-dd")
    Step ("cloud ingest_raw " + $date) {
        gcloud run jobs execute urbanpulse-ingest-raw --region $Region --project $P --args ("ingest_raw,--date," + $date) --wait
    }
}
Step "cloud forecast on the complete data" {
    gcloud run jobs execute urbanpulse-forecast --region $Region --project $P --wait
}
Step "every local observation time since the copy exists in the cloud" {
    python $tool gap --target-env $EnvFile --since $Since
}
Step "recommendations equal for dates the overlay does not reach" {
    python $tool recos-diff --target-env $EnvFile --from-days 2
}
Write-Output "80_cutover done. The local database is the rollback copy: stop it with 'supabase stop', do not reset it."
