# Registers "Fiesta KQ Bot" in Windows Task Scheduler. From then on the bot
# starts (with no window) when you log in, restarts if it crashes, and updates
# itself when new code reaches the main branch on GitHub.
#
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\install-windows-task.ps1

$ErrorActionPreference = "Stop"
$TaskName = "Fiesta KQ Bot"
$Root = Split-Path -Parent $PSScriptRoot
$PythonW = Join-Path $Root ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $PythonW)) {
    throw "Couldn't find $PythonW. Create the virtual environment first (see README)."
}
if (-not (Test-Path (Join-Path $Root ".env"))) {
    throw "Couldn't find .env in $Root. Copy .env.example to .env and add your token."
}

$Action = New-ScheduledTaskAction -Execute $PythonW -Argument "-m kqbot.supervise" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# ExecutionTimeLimit 0 = run forever (the default would stop it after 3 days).
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Runs the Fiesta KQ Bot and keeps it up to date from GitHub." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started '$TaskName'."
Write-Host "Logs: $Root\logs  (kqbot.log = the bot, supervisor.log = restarts and updates)"
