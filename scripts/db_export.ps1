# Write the local database's data to one file a teammate can load with db_import.ps1.
# Data of the public schema only; the schema itself comes from the migrations. ASCII. PowerShell 5.1.
param([string]$Out = "data\urbanpulse-db.dump", [string]$Container = "supabase_db_urbanpulse")
$Repo = Split-Path -Parent $PSScriptRoot
$target = $Out
if (-not [System.IO.Path]::IsPathRooted($target)) { $target = Join-Path $Repo $Out }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null

# Dumped inside the container and copied out: a pipe through PowerShell would corrupt the binary format.
& docker exec $Container pg_dump -U postgres -d postgres --data-only --schema=public --format=custom --file=/tmp/urbanpulse-db.dump
if ($LASTEXITCODE -ne 0) { Write-Output "pg_dump failed; is the local database running (cd app; supabase start)?"; exit 1 }
& docker cp ($Container + ":/tmp/urbanpulse-db.dump") $target
if ($LASTEXITCODE -ne 0) { Write-Output "could not copy the dump out of the container"; exit 1 }
& docker exec $Container rm -f /tmp/urbanpulse-db.dump

$size = [math]::Round((Get-Item -LiteralPath $target).Length / 1MB, 1)
Write-Output ("wrote " + $Out + " (" + $size + " MB)")
Write-Output "send this file outside git; the receiver runs scripts\db_import.ps1 <file>"
