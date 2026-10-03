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
$pythonDir = Split-Path $python -Parent
$pythonw = Join-Path $pythonDir "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

Write-Host "Project: $ProjectRoot"
Write-Host "Python : $python"

$configPath = Join-Path $ProjectRoot "config\render_sync_client.json"
if (-not (Test-Path $configPath)) {
    Write-Host ""
    Write-Host "Pairing this PC with the Render TIOM server..."
    & $python (Join-Path $ProjectRoot "scripts\pair_render_sync.py")
    if ($LASTEXITCODE -ne 0) { throw "Pairing failed. Scheduled task was not created." }
}

Write-Host ""
Write-Host "Running one test sync..."
& $python (Join-Path $ProjectRoot "scripts\pull_render_sync.py")
if ($LASTEXITCODE -ne 0) { throw "Initial sync failed. Scheduled task was not created." }

$taskName = "NMTPL Render Sync - Boot Startup"
$script = Join-Path $ProjectRoot "scripts\render_sync_worker.py"
$taskCommand = ('"{0}" "{1}"' -f $pythonw, $script)

schtasks.exe /Create /TN $taskName /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $taskCommand /F | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not create scheduled task. Run PowerShell as Administrator." }
schtasks.exe /Run /TN $taskName | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Task was created but could not be started." }

Write-Host ""
Write-Host "Render -> Base PC sync installed successfully."
Write-Host "Task   : $taskName"
Write-Host "Status : logs\render_sync\status.json"
Write-Host "Log    : logs\render_sync\worker.log"
