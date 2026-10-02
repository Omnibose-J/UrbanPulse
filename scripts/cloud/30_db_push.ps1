# SOW-MC step 4.1: apply the migrations to the target database and check the result. Idempotent.
# The URL is handed to the Supabase CLI as an argument of the child process (the CLI has no other input for it);
# it is never echoed. ASCII. PowerShell 5.1.
param([string]$EnvFile = ".env.cloud", [switch]$Plan)
. (Join-Path $PSScriptRoot "_lib.ps1")
$v = Read-EnvFile $EnvFile
Assert-Names $v @("DATABASE_URL")

Step "supabase db push (migrations in app/supabase/migrations)" {
    Push-Location -LiteralPath (Join-Path $Repo "app")
    try {
        # The CLI prints the host in its messages; keep only the lines that name a migration or the result.
        $lines = & supabase db push --db-url $v["DATABASE_URL"] --yes 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
        $lines | Where-Object { $_ -match "^(Applying migration|Finished|Remote database is up to date)" } | Write-Output
        if ($code -ne 0) { Write-Output "supabase db push failed; rerun it by hand with --debug to see why" }
        $global:LASTEXITCODE = $code
    } finally {
        Pop-Location
    }
}
Step "schema check (tables, RLS, grants)" {
    python (Join-Path $PSScriptRoot "dbtool.py") check-schema --target-env $EnvFile
}
Write-Output "30_db_push done"
