# Stops the bot and removes it from Task Scheduler.
#   powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows-task.ps1

$TaskName = "Fiesta KQ Bot"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed '$TaskName'. The bot is no longer running."
