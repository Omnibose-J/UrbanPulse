# Register or remove the UrbanPulse collect scheduled task.
# ASCII only. PowerShell 5.1. Running this twice replaces the same task.
param(
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$TaskName = "UrbanPulse collect"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "unregistered"
    exit 0
}

$Repo = Split-Path -Parent $PSScriptRoot
$PythonCmd = Get-Command python -ErrorAction Stop
$Python = $PythonCmd.Source
$LogDir = Join-Path $Repo "data\logs"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$Log = Join-Path $LogDir "collect.log"

$Now = Get-Date
$Minute = [int]([Math]::Floor($Now.Minute / 30) * 30)
$Start = Get-Date -Year $Now.Year -Month $Now.Month -Day $Now.Day -Hour $Now.Hour -Minute $Minute -Second 0
if ($Start -le $Now) {
    $Start = $Start.AddMinutes(30)
}

$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
if (-not (Test-Path -LiteralPath $CmdExe)) {
    Write-Error "cmd.exe not found"
    exit 1
}
$Arg = '/c cd /d "' + $Repo + '" && "' + $Python + '" -m engine collect >> "' + $Log + '" 2>&1'
$Action = New-ScheduledTaskAction -Execute $CmdExe -Argument $Arg -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Once -At $Start -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::FromDays(9999))
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Output ("registered " + $TaskName + " at " + $Start.ToString("yyyy-MM-dd HH:mm"))
