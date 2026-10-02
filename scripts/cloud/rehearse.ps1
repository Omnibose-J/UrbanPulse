# Dress rehearsal of SOW-MC with local stand-ins (SOW-L1). No cloud account is touched.
#   hosted database -> a throwaway container of the local stack's Postgres image, TLS on
#   GCS bucket      -> fake-gcs-server
#   Cloud Run Job   -> the engine image under the job's CPU and memory limits
# The live local database and data/raw are only read. -Keep leaves the stand-ins running.
# ASCII. PowerShell 5.1.
param([switch]$Keep)
$Plan = $false
. (Join-Path $PSScriptRoot "_lib.ps1")
Set-Location -LiteralPath $Repo

$Net = "urbanpulse-rehearsal"
$Db = "urbanpulse-rehearsal-db"
$Gcs = "urbanpulse-rehearsal-gcs"
$Cert = "urbanpulse-rehearsal-cert"
$Image = "urbanpulse-engine:rehearsal"
$Bucket = "urbanpulse-rehearsal"
$EnvName = ".env.rehearsal"
$Saved = Join-Path $env:TEMP "urbanpulse-rehearsal-recos.bin"
$tool = Join-Path $PSScriptRoot "dbtool.py"
$failed = 0

function Teardown {
    & docker rm -f $Db $Gcs 1>$null 2>$null
    & docker volume rm $Cert 1>$null 2>$null
    & docker network rm $Net 1>$null 2>$null
    Remove-Item -LiteralPath (Join-Path $Repo $EnvName), $Saved -Force -ErrorAction SilentlyContinue
}
function Check([string]$Label, [bool]$Ok, [string]$Note = "") {
    $mark = "OK  "
    if (-not $Ok) { $mark = "FAIL"; $script:failed += 1 }
    Write-Output ($mark + " " + $Label + " " + $Note)
}
function Docker-Limit([string]$Memory) { return $Memory.ToLower().Replace("i", "") }

# The two API keys go to the containers by name (`-e NAME`), never as a value on a command line.
$local = Read-EnvFile ".env"
Assert-Names $local @("SEOUL_API_KEY", "KASI_API_KEY", "DATABASE_URL")
$env:SEOUL_API_KEY = $local["SEOUL_API_KEY"]
$env:KASI_API_KEY = $local["KASI_API_KEY"]
$started = [datetime]::UtcNow

Teardown
$pgImage = (& docker inspect -f "{{.Config.Image}}" supabase_db_urbanpulse | Out-String).Trim()
if ($pgImage.Length -eq 0) { Write-Output "the local database container is not running"; exit 1 }

Step "build the engine image" { docker build -q -f app/engine/Dockerfile -t $Image . 1>$null }
Step "network and certificate volume" {
    docker network create $Net 1>$null
    docker volume create $Cert 1>$null
}
$uid = (& docker run --rm --entrypoint id $pgImage -u postgres | Out-String).Trim()
Step "self-signed certificate (the Supabase CLI only talks TLS to a remote database)" {
    $make = "openssl req -new -x509 -days 3 -nodes -subj /CN=urbanpulse-rehearsal -out /cert/server.crt -keyout /cert/server.key 2>/dev/null" +
        " && chown " + $uid + " /cert/server.key /cert/server.crt && chmod 600 /cert/server.key"
    docker run --rm --entrypoint sh -v ($Cert + ":/cert") $Image -c $make
}
Step "start the stand-in database and bucket" {
    docker run -d --name $Db --network $Net -v ($Cert + ":/cert:ro") -e POSTGRES_PASSWORD=rehearsal -p 127.0.0.1:55399:5432 $pgImage 1>$null
    docker run -d --name $Gcs --network $Net -p 127.0.0.1:55398:4443 fsouza/fake-gcs-server:1.52.2 `
        -scheme http -port 4443 -backend memory -external-url ("http://" + $Gcs + ":4443") 1>$null
}
$health = ""
for ($i = 0; $i -lt 60 -and $health -ne "healthy"; $i++) {
    Start-Sleep -Seconds 2
    $health = (& docker inspect -f "{{.State.Health.Status}}" $Db | Out-String).Trim()
}
if ($health -ne "healthy") { Write-Output "the stand-in database did not become healthy"; Teardown; exit 1 }
Step "TLS on" {
    docker exec -e PGPASSWORD=rehearsal $Db psql -h 127.0.0.1 -U supabase_admin -d postgres -q `
        -c "alter system set ssl_cert_file = '/cert/server.crt'" -c "alter system set ssl_key_file = '/cert/server.key'" `
        -c "alter system set ssl = on" -c "select pg_reload_conf()" 1>$null
}
Start-Sleep -Seconds 2
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:55398/storage/v1/b" -ContentType "application/json" -Body ('{"name":"' + $Bucket + '"}') | Out-Null

$lines = @(
    "DATABASE_URL=postgresql://postgres:rehearsal@127.0.0.1:55399/postgres",
    ("RAW_DIR=gs://" + $Bucket + "/raw")
)
[System.IO.File]::WriteAllLines((Join-Path $Repo $EnvName), $lines, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "--- database"
& (Join-Path $PSScriptRoot "30_db_push.ps1") -EnvFile $EnvName
Check "schema push" ($LASTEXITCODE -eq 0)
$again = & (Join-Path $PSScriptRoot "30_db_push.ps1") -EnvFile $EnvName | Out-String
Check "schema push, second run changes nothing" ($LASTEXITCODE -eq 0 -and $again -notmatch "Applying migration")
& (Join-Path $PSScriptRoot "31_db_copy.ps1") -EnvFile $EnvName
Check "data copy" ($LASTEXITCODE -eq 0)
& python $tool copy --target-env $EnvName | Select-Object -Last 1
Check "a second copy is refused" ($LASTEXITCODE -eq 1)

Write-Output "--- engine jobs in the image"
function Run-Job($Job, [string]$Command) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $shell = $Command + '; code=$?; echo peak_bytes=$(cat /sys/fs/cgroup/memory.peak); exit $code'
    $out = & docker run --rm --network $Net --memory (Docker-Limit $Job.Memory) --cpus $Job.Cpu `
        -e ENGINE_SKIP_DOTENV=1 -e TZ=Asia/Seoul -e SEOUL_API_KEY -e KASI_API_KEY `
        -e ("DATABASE_URL=postgresql://postgres:rehearsal@" + $Db + ":5432/postgres") `
        -e ("RAW_DIR=gs://" + $Bucket + "/raw") -e ("STORAGE_EMULATOR_HOST=http://" + $Gcs + ":4443") `
        --entrypoint sh $Image -c $shell 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $peak = 0
    $match = $out | Select-String -Pattern "peak_bytes=(\d+)" | Select-Object -Last 1
    if ($null -ne $match) { $peak = [int64]$match.Matches[0].Groups[1].Value }
    $note = ("{0}s, peak {1} MB of {2}, {3} CPU" -f [int]$watch.Elapsed.TotalSeconds, [int]($peak / 1MB), $Job.Memory, $Job.Cpu)
    Check $Job.Name ($code -eq 0) $note
    if ($code -ne 0) { $out | Select-Object -Last 5 | Write-Output }
}
function Find-Job([string]$Name) { return ($EngineJobs | Where-Object { $_.Name -eq $Name }) }

# The two forecasts below must fall in the same clock hour: today's rows depend on the hours still ahead.
$minute = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([datetime]::UtcNow, "Korea Standard Time").Minute
if ($minute -ge 53) { Start-Sleep -Seconds ((60 - $minute) * 60 + 20) }
Run-Job (Find-Job "urbanpulse-healthcheck") "python -W ignore -m engine healthcheck"
Run-Job (Find-Job "urbanpulse-collect") "python -W ignore -m engine collect"
Run-Job (Find-Job "urbanpulse-forecast") "python -W ignore -m engine forecast"
& python $tool recos-save --target-env $EnvName --from-days 1 --out $Saved
$env:ENGINE_ENV_FILE = $EnvName
& python -m engine forecast 1>$null 2>$null
$hostForecast = $LASTEXITCODE
Remove-Item Env:ENGINE_ENV_FILE
Check "the same forecast run on Windows against the same data" ($hostForecast -eq 0)
& python $tool recos-diff --target-env $EnvName --from-days 1 --against $Saved
Check "image and laptop build identical recommendations from the same data" ($LASTEXITCODE -eq 0)
Run-Job (Find-Job "urbanpulse-evaluate") "python -W ignore -m engine evaluate"
Run-Job (Find-Job "urbanpulse-ingest-raw") "python -W ignore -m engine ingest_raw"

Write-Output "--- raw objects"
$once = Get-Content -LiteralPath (Join-Path $PSScriptRoot "rehearse_write_once.py") -Raw
$once | & docker run --rm -i --network $Net -e ("RAW_DIR=gs://" + $Bucket + "/raw") -e ("STORAGE_EMULATOR_HOST=http://" + $Gcs + ":4443") `
    --entrypoint python $Image -W ignore -
Check "an existing object is not replaced" ($LASTEXITCODE -eq 0)
$listing = Invoke-RestMethod -Uri ("http://127.0.0.1:55398/storage/v1/b/" + $Bucket + "/o?maxResults=5000")
$objects = @($listing.items | Where-Object { $_.name -like "raw/*/*.json.gz" -and $_.name -notlike "*ONCE*" }).Count
Check "collect wrote its snapshots to the bucket" ($objects -ge 100) ($objects.ToString() + " objects")

Write-Output "--- against the live local database"
& python $tool recos-diff --target-env $EnvName --from-days 2
Check "stand-in and live recommendations agree where the overlay does not reach" ($LASTEXITCODE -eq 0)
$since = $started.ToString("yyyy-MM-dd HH:mm:ss")
& python $tool runs-since --target-env .env --since $since --job "healthcheck,forecast,evaluate,ingest_raw"
Check "the live ledger has no run from the rehearsal" ($LASTEXITCODE -eq 0)

if ($Keep) {
    Write-Output ("stand-ins left running; env file " + $EnvName)
} else {
    Teardown
    $left = (& docker ps -a --filter "name=urbanpulse-rehearsal" --format "{{.Names}}" | Out-String).Trim()
    Check "nothing left behind" ($left.Length -eq 0 -and -not (Test-Path -LiteralPath (Join-Path $Repo $EnvName)))
}
Write-Output ($failed.ToString() + " failed")
if ($failed -gt 0) { exit 1 }
exit 0
