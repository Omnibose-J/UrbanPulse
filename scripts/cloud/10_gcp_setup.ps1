# SOW-MC step 3: APIs, image repository, raw bucket, service accounts. Idempotent. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT")
$P = $v["GCP_PROJECT"]
$bucket = "gs://" + (Bucket-Name $v)
$engine = Engine-Account $v
$scheduler = Scheduler-Account $v
$policy = Join-Path $PSScriptRoot "ar_cleanup_policy.json"

Step "enable APIs (run, scheduler, artifact registry, secret manager, storage)" {
    gcloud services enable run.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com --project $P
}
Ensure "artifact repository urbanpulse" {
    gcloud artifacts repositories describe urbanpulse --location $Region --project $P
} {
    gcloud artifacts repositories create urbanpulse --repository-format docker --location $Region --project $P
}
Step "image cleanup policy: keep the 3 newest" {
    gcloud artifacts repositories set-cleanup-policies urbanpulse --location $Region --project $P --policy $policy --no-dry-run
}
Ensure ("bucket " + $bucket) {
    gcloud storage buckets describe $bucket --project $P
} {
    gcloud storage buckets create $bucket --project $P --location $Region --uniform-bucket-level-access --public-access-prevention
}
Step "bucket versioning on" { gcloud storage buckets update $bucket --versioning --project $P }
Ensure "service account urbanpulse-engine" {
    gcloud iam service-accounts describe $engine --project $P
} {
    gcloud iam service-accounts create urbanpulse-engine --display-name "UrbanPulse engine jobs" --project $P
}
Ensure "service account urbanpulse-scheduler" {
    gcloud iam service-accounts describe $scheduler --project $P
} {
    gcloud iam service-accounts create urbanpulse-scheduler --display-name "UrbanPulse scheduler" --project $P
}
# Creator + viewer only: the engine can add and read objects, never delete or replace one.
foreach ($role in @("roles/storage.objectCreator", "roles/storage.objectViewer")) {
    Step ("bucket role " + $role + " for urbanpulse-engine") {
        gcloud storage buckets add-iam-policy-binding $bucket --member ("serviceAccount:" + $engine) --role $role --project $P 1>$null
    }
}
Write-Output "10_gcp_setup done"
