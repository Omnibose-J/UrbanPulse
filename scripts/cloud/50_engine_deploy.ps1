# SOW-MC step 6: build and push the engine image, deploy the Cloud Run Jobs, optionally execute them once.
# Idempotent: an image tag that is already in the repository is not rebuilt; `jobs deploy` updates in place.
# ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan, [switch]$Execute)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT")
$P = $v["GCP_PROJECT"]
$engine = Engine-Account $v
$rawDir = "gs://" + (Bucket-Name $v) + "/raw"
Set-Location -LiteralPath $Repo

$dirty = (& git status --porcelain | Out-String).Trim()
if ($dirty.Length -gt 0 -and -not $Plan) {
    Write-Output "the working tree is not clean; commit first so the image tag names what it holds"
    exit 1
}
$sha = (& git rev-parse --short HEAD | Out-String).Trim()
$image = $Region + "-docker.pkg.dev/" + $P + "/urbanpulse/engine:" + $sha
Write-Output ("image tag engine:" + $sha)

Step "docker credential helper for the region" { gcloud auth configure-docker ($Region + "-docker.pkg.dev") --quiet }
Ensure ("image engine:" + $sha + " in the repository") {
    gcloud artifacts docker images describe $image --project $P
} {
    docker build -f app/engine/Dockerfile -t $image .
    if ($LASTEXITCODE -eq 0) { docker push $image }
}

$secrets = ($EngineSecrets | ForEach-Object { $_.Name + "=" + $_.Secret + ":latest" }) -join ","
foreach ($job in $EngineJobs) {
    $name = $job.Name
    $jobArgs = $job.JobArgs
    $cpu = $job.Cpu
    $memory = $job.Memory
    $timeout = $job.Timeout
    # max-retries 0: a retry of collect would write a second run folder; the next slot is the retry.
    Step ("deploy job " + $name) {
        gcloud run jobs deploy $name --image $image --region $Region --project $P `
            --service-account $engine --set-secrets $secrets `
            --set-env-vars ("RAW_DIR=" + $rawDir + ",TZ=Asia/Seoul") `
            --args $jobArgs --cpu $cpu --memory $memory --task-timeout $timeout --max-retries 0 --quiet 1>$null
    }
}

if ($Execute) {
    foreach ($name in @("urbanpulse-healthcheck", "urbanpulse-collect", "urbanpulse-forecast", "urbanpulse-evaluate")) {
        Step ("execute " + $name + " and wait") {
            gcloud run jobs execute $name --region $Region --project $P --wait
        }
    }
}
Write-Output "50_engine_deploy done"
