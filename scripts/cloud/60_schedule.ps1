# SOW-MC step 7: Cloud Scheduler triggers for four jobs, time zone Asia/Seoul. Idempotent.
# -Pause / -Resume switch every trigger off or on (runbook: "pause all schedules"). ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan, [switch]$Pause, [switch]$Resume)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT")
$P = $v["GCP_PROJECT"]
$scheduler = Scheduler-Account $v

# No trigger for ingest-raw, healthcheck, tier_b, rejudge: those are run by hand.
# integrity runs hourly at :45 (after the half-hour collect) so a broken invariant fails an execution and the
# failed-execution alert (65_alerts.ps1) reaches the operator without anyone watching the admin screen.
$schedules = @(
    @{ Job = "urbanpulse-collect";       Cron = "*/30 * * * *" },
    @{ Job = "urbanpulse-forecast";      Cron = "10 5 * * *" },
    @{ Job = "urbanpulse-evaluate";      Cron = "0 6 * * *" },
    @{ Job = "urbanpulse-sync-holidays"; Cron = "0 4 * * 1" },
    @{ Job = "urbanpulse-integrity";     Cron = "45 * * * *" }
)

foreach ($item in $schedules) {
    $job = $item.Job
    $cron = $item.Cron
    if ($Pause -or $Resume) {
        $verb = "resume"
        if ($Pause) { $verb = "pause" }
        Step ($verb + " trigger " + $job) { gcloud scheduler jobs $verb $job --location $Region --project $P 1>$null }
        continue
    }
    $uri = "https://run.googleapis.com/v2/projects/" + $P + "/locations/" + $Region + "/jobs/" + $job + ":run"
    Step ("invoker role on " + $job + " for urbanpulse-scheduler") {
        gcloud run jobs add-iam-policy-binding $job --region $Region --project $P --member ("serviceAccount:" + $scheduler) --role roles/run.invoker 1>$null
    }
    if ($Plan) { Write-Output ("plan  trigger " + $job + " [" + $cron + "] create or update"); continue }
    & gcloud scheduler jobs describe $job --location $Region --project $P 1>$null 2>$null
    $verb = "create"
    if ($LASTEXITCODE -eq 0) { $verb = "update" }
    Step ("trigger " + $job + " [" + $cron + "] " + $verb) {
        gcloud scheduler jobs $verb http $job --location $Region --project $P --schedule $cron --time-zone "Asia/Seoul" `
            --uri $uri --http-method POST --oauth-service-account-email $scheduler 1>$null
    }
}
if (-not $Plan) {
    gcloud scheduler jobs list --location $Region --project $P --format "table(name.basename(),schedule,timeZone,state)"
}
Write-Output "60_schedule done"
