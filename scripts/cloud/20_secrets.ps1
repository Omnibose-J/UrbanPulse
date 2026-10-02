# SOW-MC step 3: Secret Manager. A new version is added only when the value differs. Prints names only.
# ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v (@("GCP_PROJECT") + ($EngineSecrets | ForEach-Object { $_.Name }))
$P = $v["GCP_PROJECT"]
$engine = Engine-Account $v

foreach ($item in $EngineSecrets) {
    $secret = $item.Secret
    $value = $v[$item.Name]
    Ensure ("secret " + $secret) {
        gcloud secrets describe $secret --project $P
    } {
        gcloud secrets create $secret --replication-policy user-managed --locations $Region --project $P
    }
    if ($Plan) {
        Write-Output ("plan  add a version of " + $secret + " when the value differs")
    } else {
        # The current value stays in this variable only; it is compared, never written out.
        $current = (& gcloud secrets versions access latest --secret $secret --project $P 2>$null | Out-String)
        $hasVersion = ($LASTEXITCODE -eq 0)
        if ($hasVersion -and $current.TrimEnd("`r", "`n") -ceq $value) {
            Write-Output ($secret + " unchanged")
        } else {
            With-SecretFile $value { param($file)
                gcloud secrets versions add $secret --data-file $file --project $P 1>$null
            }
            if ($LASTEXITCODE -ne 0) { Write-Output ("FAIL  add version " + $secret); exit 1 }
            Write-Output ($secret + " updated")
        }
        $current = $null
    }
    Step ("accessor role on " + $secret + " for urbanpulse-engine") {
        gcloud secrets add-iam-policy-binding $secret --member ("serviceAccount:" + $engine) --role roles/secretmanager.secretAccessor --project $P 1>$null
    }
}
Write-Output "20_secrets done"
