# NMTPL office PC: move existing cloud-sync tasks to hourly 06:00–22:00 IST.
# Safe preview by default; -Apply backs up the task XML before changing triggers.
# No database rows, sync state, OAuth tokens, or WB mail tasks are touched.
[CmdletBinding()]
param(
  [switch]$Apply,
  [string]$ProjectRoot = 'E:\NMTPL_Server_v0_1_Laptop_Test\NMTPL_Server_v0_1'
)
$ErrorActionPreference = 'Stop'
if ((Get-TimeZone).Id -ne 'India Standard Time') {
  throw "Safety stop: PC time zone must be India Standard Time (IST)."
}
$plans = @(
  @{ Name = 'NMTPL Render Sync - Every 3 Minutes'; Pattern = 'run_render_sync_once[.]cmd'; Required = $true },
  @{ Name = 'NMTPL Despatch Mirror - Every 5 Minutes'; Pattern = 'pc_despatch_mirror_standalone[.]py'; Required = $false }
)
$bootName = 'NMTPL Render Sync - Boot Catchup'
$found = @()
foreach ($plan in $plans) {
  $task = Get-ScheduledTask -TaskName $plan.Name -ErrorAction SilentlyContinue
  if ($null -eq $task) {
    if ($plan.Required) { throw "Required PC sync task missing: $($plan.Name). Nothing changed." }
    Write-Host "Skipping optional task (not installed): $($plan.Name)"
    continue
  }
  $action = (($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' ')
  if ($action -notmatch $plan.Pattern) { throw "Safety stop: unexpected task action for $($plan.Name): $action" }
  $found += @{Name = $plan.Name; Task = $task}
  Write-Host "Found $($plan.Name): $action"
}
$boot = Get-ScheduledTask -TaskName $bootName -ErrorAction SilentlyContinue
if ($null -ne $boot) {
  $bootAction = (($boot.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' ')
  if ($bootAction -notmatch 'run_render_sync_once[.]cmd') {
    throw "Safety stop: unexpected boot task action: $bootAction"
  }
  Write-Host "Found boot catchup task; it will be disabled to avoid out-of-hours cloud wakeups."
}
Write-Host "Requested: 17 daily hourly slots, 06:00 through 22:00 IST, inclusive."
if (-not $Apply) {
  Write-Host "PREVIEW ONLY: no changes. Re-run with -Apply on the office PC."
  return
}
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
  throw "PC project root missing: $ProjectRoot"
}
$backup = Join-Path $ProjectRoot ('backups\pc_hourly_sync_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($item in $found) {
  $safe = ($item.Name -replace '[^a-zA-Z0-9._-]', '_')
  Export-ScheduledTask -TaskName $item.Name | Out-File (Join-Path $backup ($safe+'.xml')) -Encoding Unicode
}
if ($null -ne $boot) {
  Export-ScheduledTask -TaskName $bootName | Out-File (Join-Path $backup 'boot_catchup.xml') -Encoding Unicode
}
$triggers = @(6..22 | ForEach-Object {
  New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($_))
})
$changed = @()
try {
  foreach ($item in $found) {
    $settings = $item.Task.Settings
    $settings.StartWhenAvailable = $false
    Set-ScheduledTask -TaskName $item.Name -Trigger $triggers -Settings $settings -ErrorAction Stop | Out-Null
    $changed += $item
    $after = Get-ScheduledTask -TaskName $item.Name -ErrorAction Stop
    $hours = @($after.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).Hour } | Sort-Object -Unique)
    if ($hours.Count -ne 17 -or ($hours -join ',') -ne ((6..22) -join ',')) {
      throw "Schedule verification failed: $($item.Name)"
    }
    Write-Host "VERIFIED: $($item.Name) -> hourly 06:00–22:00"
  }
  if ($null -ne $boot) {
    Disable-ScheduledTask -TaskName $bootName -ErrorAction Stop | Out-Null
    Write-Host "VERIFIED: boot catchup disabled; no sync outside the daily hourly schedule."
  }
} catch {
  foreach ($item in $changed) {
    $safe = ($item.Name -replace '[^a-zA-Z0-9._-]', '_')
    $path = Join-Path $backup ($safe+'.xml')
    try {
      Register-ScheduledTask -TaskName $item.Name -Xml (Get-Content -LiteralPath $path -Raw) -Force -ErrorAction Stop | Out-Null
    } catch { Write-Warning "Manual restore needed for $($item.Name), XML: $path" }
  }
  throw
}
Write-Host "DONE. Original Task Scheduler backups: $backup"
Write-Host "Important: changes were made to THIS PC only; the cloud sync credentials/cursors were preserved."
