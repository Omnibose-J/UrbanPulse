# SOW-MC step 5: upload data/raw to the bucket. Nothing is deleted at the destination. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("GCP_PROJECT")
$P = $v["GCP_PROJECT"]
$target = "gs://" + (Bucket-Name $v) + "/raw"
$local = Join-Path $Repo "data\raw"

if ($Plan) {
    Write-Output "plan  count local files under data/raw"
} else {
    # Counted before the upload: collect keeps adding folders while this runs.
    $files = Get-ChildItem -LiteralPath $local -Recurse -File -Filter "*.json.gz"
    $localCount = $files.Count
    $localBytes = ($files | Measure-Object -Property Length -Sum).Sum
    Write-Output ("local  objects " + $localCount + " bytes " + $localBytes)
}
Step ("rsync data/raw -> " + $target + " (no delete)") {
    gcloud storage rsync $local $target --recursive --project $P
}
if ($Plan) {
    Write-Output "plan  compare object count and bytes"
} else {
    $remote = & gcloud storage ls --recursive ($target + "/**") --project $P 2>$null
    $remoteCount = @($remote | Where-Object { $_ -like "*.json.gz" }).Count
    $du = (& gcloud storage du --summarize $target --project $P 2>$null | Out-String).Trim()
    $remoteBytes = [int64](($du -split "\s+")[0])
    Write-Output ("bucket objects " + $remoteCount + " bytes " + $remoteBytes)
    if ($remoteCount -lt $localCount -or $remoteBytes -lt $localBytes) {
        Write-Output "FAIL  the bucket holds less than the local folder did"
        exit 1
    }
}
Write-Output "40_raw_upload done"
