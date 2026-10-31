# Safe Task Scheduler change for the standalone PC Despatch mirror.
# Preview by default. Use -Apply only on the office PC after checking the task.
# Does not edit the worker's sync cursors, local database, or other schedules.
[CmdletBinding()]
param(
  [switch]$Apply,
  [string]$TaskName = 'NMTPL Despatch Mirror - Every 5 Minutes'
)
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$command = (($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' ')
if ($command -notmatch 'pc_despatch_mirror_standalone[.]py') {
  throw "Safety stop: task does not launch the Despatch standalone mirror. Actual action: $command"
}
Write-Host "Task: $TaskName"
Write-Host "Action: $command"
Write-Host "New times: every day, 06:00,07:00,...,22:00 IST (17 runs)"
if (-not $Apply) {
  Write-Host 'Preview only. No changes. Re-run with -Apply to back up and install the hourly triggers.'
  return
}
$root = 'E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1'
$backup = Join-Path $root ('backups\pc_sync_schedule_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$xml = Join-Path $backup 'despatch_mirror_original_task.xml'
Export-ScheduledTask -TaskName $TaskName | Out-File -FilePath $xml -Encoding Unicode
$triggers = @(6..22 | ForEach-Object {
  New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($_))
})
Set-ScheduledTask -TaskName $TaskName -Trigger $triggers -ErrorAction Stop | Out-Null
$after = Get-ScheduledTask -TaskName $TaskName
$hours = @($after.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).Hour } | Sort-Object -Unique)
if ($hours.Count -ne 17 -or ($hours -join ',') -ne ((6..22) -join ',')) {
  throw "Verification failed. Original XML backup: $xml"
}
Write-Host "VERIFIED: $($hours.Count) daily hourly triggers, 06:00–22:00."
Write-Host "Original task backup: $xml"
Write-Host 'Note: the main long-running PC sync worker must use the updated scripts/render_sync_worker.py code to observe the same window.'
