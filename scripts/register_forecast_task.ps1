# Register or remove the UrbanPulse forecast scheduled task.
# ASCII only. PowerShell 5.1. Running this twice replaces the same task.
param(
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$TaskName = "UrbanPulse forecast"

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
$Log = Join-Path $LogDir "forecast.log"

$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
if (-not (Test-Path -LiteralPath $CmdExe)) {
    Write-Error "cmd.exe not found"
    exit 1
}
$Arg = '/c cd /d "' + $Repo + '" && "' + $Python + '" -m engine forecast >> "' + $Log + '" 2>&1'
$Action = New-ScheduledTaskAction -Execute $CmdExe -Argument $Arg -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Daily -At "05:00"
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Output ("registered " + $TaskName + " at 05:00")
