# Register the UrbanPulse evaluate task. ASCII only. PowerShell 5.1.
param(
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$TaskName = "UrbanPulse evaluate"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "unregistered"
    exit 0
}

$Repo = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source
$LogDir = Join-Path $Repo "data\logs"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$Log = Join-Path $LogDir "evaluate.log"
$CmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
$Arg = '/c cd /d "' + $Repo + '" && "' + $Python + '" -m engine evaluate >> "' + $Log + '" 2>&1'
$Action = New-ScheduledTaskAction -Execute $CmdExe -Argument $Arg -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Output ("registered " + $TaskName + " at 06:00")
