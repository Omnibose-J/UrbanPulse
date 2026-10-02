# Load a file written by db_export.ps1 into the local database.
# Run after `cd app; supabase start` on a fresh clone. Refuses a database that already holds places: rows are never merged.
# ASCII. PowerShell 5.1.
param([Parameter(Mandatory = $true)][string]$File, [string]$Container = "supabase_db_urbanpulse")
if (-not (Test-Path -LiteralPath $File)) { Write-Output ("no such file: " + $File); exit 1 }

$count = (& docker exec $Container psql -U postgres -d postgres -At -c "select count(*) from public.places" | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { Write-Output "cannot read the local database; run 'supabase start' in app/ first"; exit 1 }
if ($count -ne "0") { Write-Output ("the database already has " + $count + " places; nothing was loaded"); exit 1 }

& docker cp $File ($Container + ":/tmp/urbanpulse-db.dump")
if ($LASTEXITCODE -ne 0) { Write-Output "could not copy the file into the container"; exit 1 }
& docker exec $Container pg_restore -U postgres -d postgres --data-only --single-transaction --exit-on-error /tmp/urbanpulse-db.dump
$code = $LASTEXITCODE
& docker exec $Container rm -f /tmp/urbanpulse-db.dump
if ($code -ne 0) { Write-Output "pg_restore failed; nothing was loaded (one transaction)"; exit 1 }

& docker exec $Container psql -U postgres -d postgres -At -F " " -c "select 'places', count(*) from public.places union all select 'live_obs', count(*) from public.live_obs union all select 'recommendations', count(*) from public.recommendations"
Write-Output "loaded. Next: python -m engine collect; python -m engine forecast"
