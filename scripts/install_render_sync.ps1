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

$everyTask = "NMTPL Render Sync - Every 3 Minutes"
$bootTask = "NMTPL Render Sync - Boot Catchup"

schtasks.exe /Delete /TN "NMTPL Render Sync - Boot Startup" /F *> $null
schtasks.exe /Delete /TN $everyTask /F *> $null
schtasks.exe /Delete /TN $bootTask /F *> $null

Write-Host ""
Write-Host "Creating SYSTEM sync task every 3 minutes..."
schtasks.exe /Create /TN $everyTask /SC MINUTE /MO 3 /RU SYSTEM /RL HIGHEST /TR ('"' + $runner + '"') /F | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the 3-minute sync task. Run PowerShell as Administrator."
}

Write-Host "Creating SYSTEM boot catch-up task..."
schtasks.exe /Create /TN $bootTask /SC ONSTART /RU SYSTEM /RL HIGHEST /TR ('"' + $runner + '"') /F | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the boot catch-up task."
}

Write-Host "Running scheduled sync now..."
schtasks.exe /Run /TN $everyTask | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Tasks were created but the test scheduled run could not be started."
}

Start-Sleep -Seconds 8
$last = schtasks.exe /Query /TN $everyTask /V /FO LIST
$last | Out-Host

Write-Host ""
Write-Host "Render -> Base PC sync installed in boot-safe mode."
Write-Host "Tasks  : $everyTask"
Write-Host "         $bootTask"
Write-Host "Status : logs\render_sync\status.json"
Write-Host "Log    : logs\render_sync\scheduler.log"
