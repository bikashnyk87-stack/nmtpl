param([string]$ProjectRoot = "")

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}

Write-Host "Project: $ProjectRoot"
Write-Host "Python : $python"

$configPath = Join-Path $ProjectRoot "config\render_sync_client.json"
if (-not (Test-Path $configPath)) {
    Write-Host ""
    Write-Host "Pairing this PC with the Render TIOM server..."
    & $python (Join-Path $ProjectRoot "scripts\pair_render_sync.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Pairing failed. Scheduled tasks were not created."
    }
}

Write-Host ""
Write-Host "Running one verified sync before scheduling..."
& $python (Join-Path $ProjectRoot "scripts\pull_render_sync.py")
if ($LASTEXITCODE -ne 0) {
    throw "Initial sync failed. Scheduled tasks were not created."
}

$runner = Join-Path $ProjectRoot "scripts\run_render_sync_once.cmd"
if (-not (Test-Path $runner)) {
    throw "Sync runner is missing: $runner"
}

# Preserve the legacy task name so existing PC installations and helper scripts
# can find it, but install only 17 hourly daily IST triggers.
if ((Get-TimeZone).Id -ne 'India Standard Time') {
    throw "Safety stop: set Windows time zone to India Standard Time before scheduling."
}
$everyTask = "NMTPL Render Sync - Every 3 Minutes"
$bootTask = "NMTPL Render Sync - Boot Catchup"
$backupDir = Join-Path $ProjectRoot ("backups\\render_sync_hourly_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
foreach ($name in @($everyTask,$bootTask)) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        $actionLine = (($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' ')
        if ($actionLine -notmatch 'run_render_sync_once[.]cmd') {
            throw "Safety stop: unexpected action on $name. Existing task unchanged: $actionLine"
        }
        Export-ScheduledTask -TaskName $name |
            Out-File (Join-Path $backupDir (($name -replace '[^a-zA-Z0-9._-]','_')+'.xml')) -Encoding Unicode
    }
}
Write-Host "Scheduling SYSTEM sync hourly, 06:00–22:00 IST..."
$triggers = @(6..22 | ForEach-Object {
    New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($_))
})
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c "'+$runner+'"') -WorkingDirectory $ProjectRoot
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable:$false -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $everyTask -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
$verify = Get-ScheduledTask -TaskName $everyTask
$hours = @($verify.Triggers | ForEach-Object { ([datetime]$_.StartBoundary).Hour } | Sort-Object -Unique)
if ($hours.Count -ne 17 -or ($hours -join ',') -ne ((6..22) -join ',')) {
    throw "Hourly sync trigger verification failed. Task XML backup: $backupDir"
}
$boot = Get-ScheduledTask -TaskName $bootTask -ErrorAction SilentlyContinue
if ($null -ne $boot) {
    Disable-ScheduledTask -TaskName $bootTask -ErrorAction Stop | Out-Null
}
Write-Host "VERIFIED: Render/PC sync 17 times per day (06–22 inclusive), no three-minute or boot poll."
Write-Host "Task: $everyTask (legacy label; hourly triggers)"
Write-Host "Backups : $backupDir"
Write-Host "Status  : logs\\render_sync\\status.json"
Write-Host "Log     : logs\\render_sync\\scheduler.log"
