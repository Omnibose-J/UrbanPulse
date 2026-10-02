# SOW-MC step 9: link app/web to a Vercel project, set the three production variables, deploy.
# Values reach Vercel through a file the CLI reads on stdin; names only are printed. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
$names = @("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ADMIN_TOKEN")
Assert-Names $v $names
$web = Join-Path $Repo "app\web"

Step "vercel link (project urbanpulse, root app/web)" { vercel link --yes --project urbanpulse --cwd $web 1>$null }
foreach ($name in $names) {
    if ($Plan) { Write-Output ("plan  set production variable " + $name); continue }
    # Remove-then-add replaces a value on every CLI version; a missing variable makes the remove fail, which is fine.
    & vercel env rm $name production --yes --cwd $web 1>$null 2>$null
    With-SecretFile $v[$name] { param($file)
        cmd /c ("vercel env add " + $name + " production --cwd `"" + $web + "`" < `"" + $file + "`"") 1>$null 2>$null
    }
    if ($LASTEXITCODE -ne 0) { Write-Output ("FAIL  set " + $name); exit 1 }
    Write-Output ("set   " + $name)
}
Step "vercel deploy --prod" { vercel deploy --prod --yes --cwd $web }
Write-Output "70_web_deploy done; pass the printed URL to 90_verify.ps1"
